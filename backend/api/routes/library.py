"""Song library endpoints."""

from pathlib import Path
import re
import struct
import wave
from uuid import uuid4
from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse

from api.deps import SessionDep, UserDep
from core.config import settings
from repositories.radio import RadioRepository
from schemas.radio import BatchUploadOut, SongCreate, SongOut
from services.radio import RadioService

router = APIRouter(prefix="/library", tags=["library"])
_allowed_content_types = {
    "audio/mpeg",
    "audio/mp3",
    "audio/wav",
    "audio/ogg",
    "audio/mp4",
    "audio/x-wav",
    "audio/x-m4a",
    "audio/aac",
    "audio/x-aac",
    "audio/flac",
    "audio/x-flac",
}
_allowed_audio_extensions = {".mp3", ".wav", ".ogg", ".mp4", ".m4a", ".aac", ".flac"}


def _is_audio_file(file: UploadFile) -> bool:
    """Return whether the file is a recognized audio format by extension or MIME type."""
    extension = Path(file.filename or "").suffix.lower()
    content_type = (file.content_type or "").lower().strip()
    return extension in _allowed_audio_extensions or content_type in _allowed_content_types


def _first_tag(metadata: object, name: str) -> str | None:
    """Return the first non-empty easy-ID3/Vorbis tag value."""
    if not hasattr(metadata, "get"):
        return None
    values = metadata.get(name, [])
    if isinstance(values, str):
        return values.strip() or None
    if isinstance(values, (list, tuple)):
        for value in values:
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def _fallback_name(filename: str) -> tuple[str, str]:
    """Build useful metadata from common `Artist - Title` filenames."""
    stem = Path(filename).stem
    cleaned = re.sub(r"[_]+", " ", stem).strip()
    parts = re.split(r"\s+-\s+", cleaned, maxsplit=1)
    if len(parts) == 2 and all(parts):
        return parts[1], parts[0]
    return cleaned or "Untitled audio", "Unknown Artist"


def _decode_id3_text(raw: bytes) -> str | None:
    """Decode a compact ID3 text frame without a third-party package."""
    if len(raw) < 2:
        return None
    encoding = raw[0]
    codecs = {0: "latin-1", 1: "utf-16", 2: "utf-16-be", 3: "utf-8"}
    try:
        value = raw[1:].decode(codecs.get(encoding, "utf-8"), errors="replace").replace("\x00", "").strip()
        return value or None
    except UnicodeDecodeError:
        return None


def _read_id3v2(path: Path) -> tuple[str | None, str | None]:
    """Read common MP3 title/artist ID3v2 frames from the file header."""
    try:
        with path.open("rb") as audio_file:
            header = audio_file.read(10)
            if len(header) != 10 or header[:3] != b"ID3":
                return None, None
            version = header[3]
            tag_size = sum((byte & 0x7F) << (7 * (3 - index)) for index, byte in enumerate(header[6:10]))
            payload = audio_file.read(min(tag_size, 2_000_000))
    except OSError:
        return None, None
    title: str | None = None
    artist: str | None = None
    offset = 0
    while offset + 10 <= len(payload):
        frame_id = payload[offset:offset + 4].decode("ascii", errors="ignore")
        if not frame_id.strip("\x00"):
            break
        size_bytes = payload[offset + 4:offset + 8]
        frame_size = int.from_bytes(size_bytes, "big") if version == 3 else sum((byte & 0x7F) << (7 * (3 - index)) for index, byte in enumerate(size_bytes))
        frame_end = offset + 10 + frame_size
        if frame_size <= 0 or frame_end > len(payload):
            break
        if frame_id == "TIT2":
            title = _decode_id3_text(payload[offset + 10:frame_end])
        elif frame_id == "TPE1":
            artist = _decode_id3_text(payload[offset + 10:frame_end])
        offset = frame_end
    return title, artist


_MP3_BITRATES_V1_L1 = (0, 32, 64, 96, 128, 160, 192, 224, 256, 288, 320, 352, 384, 416, 448, 0)
_MP3_BITRATES_V1_L2 = (0, 32, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 384, 0)
_MP3_BITRATES_V1_L3 = (0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 0)
_MP3_BITRATES_V2_L1 = (0, 32, 48, 56, 64, 80, 96, 112, 128, 144, 160, 176, 192, 224, 256, 0)
_MP3_BITRATES_V2_L23 = (0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160, 0)
_MP3_SAMPLERATES_V1 = (44100, 48000, 32000, 0)
_MP3_SAMPLERATES_V2 = (22050, 24000, 16000, 0)
_MP3_SAMPLERATES_V25 = (11025, 12000, 8000, 0)


def _parse_mp3_frame(data: bytes, offset: int) -> tuple[int, int, int, int, int] | None:
    """Parse one MPEG audio frame header and return (frame_bytes, samples_per_frame, sample_rate, version_bits, channel_mode)."""
    if offset + 4 > len(data) or data[offset] != 0xFF or (data[offset + 1] & 0xE0) != 0xE0:
        return None
    header = struct.unpack(">I", data[offset:offset + 4])[0]
    ver_bits = (header >> 19) & 0x3
    layer_bits = (header >> 17) & 0x3
    br_idx = (header >> 12) & 0xF
    sr_idx = (header >> 10) & 0x3
    pad = (header >> 9) & 0x1
    chan = (header >> 6) & 0x3
    if ver_bits == 1 or layer_bits == 0 or br_idx in (0, 15) or sr_idx == 3:
        return None
    if ver_bits == 3:
        sr = _MP3_SAMPLERATES_V1[sr_idx]
        spf = 384 if layer_bits == 3 else 1152
        br_table = _MP3_BITRATES_V1_L1 if layer_bits == 3 else (_MP3_BITRATES_V1_L2 if layer_bits == 2 else _MP3_BITRATES_V1_L3)
    else:
        sr = _MP3_SAMPLERATES_V2[sr_idx] if ver_bits == 2 else _MP3_SAMPLERATES_V25[sr_idx]
        spf = 384 if layer_bits == 3 else (1152 if layer_bits == 2 else 576)
        br_table = _MP3_BITRATES_V2_L1 if layer_bits == 3 else (_MP3_BITRATES_V1_L2 if layer_bits == 2 else _MP3_BITRATES_V2_L23)
    br = br_table[br_idx] * 1000
    if sr <= 0 or br <= 0:
        return None
    if layer_bits == 3:
        flen = (12 * br // sr + pad) * 4
    else:
        flen = (144 * br // sr) + pad if spf == 1152 else (72 * br // sr) + pad
    if flen < 4:
        return None
    return flen, spf, sr, ver_bits, chan


def _read_mp3_duration(path: Path) -> float:
    """Compute MP3 duration in seconds using Xing/VBRI headers or MPEG frame scanning."""
    try:
        data = path.read_bytes()
    except OSError:
        return 0.0
    size = len(data)
    offset = 0
    if size >= 10 and data[:3] == b"ID3":
        tag_size = ((data[6] & 0x7F) << 21) | ((data[7] & 0x7F) << 14) | ((data[8] & 0x7F) << 7) | (data[9] & 0x7F)
        offset = 10 + tag_size + (10 if (data[5] & 0x10) else 0)
    total_dur = 0.0
    frames = 0
    i = offset
    while i + 4 <= size:
        parsed = _parse_mp3_frame(data, i)
        if parsed:
            flen, spf, sr, ver_bits, chan = parsed
            if frames == 0:
                # Require consecutive frame lock (or near-EOF single frame) to avoid syncing on embedded image bytes
                has_next_lock = (i + flen + 4 <= size and _parse_mp3_frame(data, i + flen) is not None)
                near_eof = size - (i + flen) <= 256
                if not has_next_lock and not near_eof:
                    i += 1
                    continue
                side_info = 17 if (ver_bits == 3 and chan == 3) else (32 if ver_bits == 3 else (9 if chan == 3 else 17))
                xoff = i + 4 + side_info
                if xoff + 12 <= size and data[xoff:xoff + 4] in (b"Xing", b"Info"):
                    flags = struct.unpack(">I", data[xoff + 4:xoff + 8])[0]
                    if flags & 0x1:
                        xframes = struct.unpack(">I", data[xoff + 8:xoff + 12])[0]
                        if xframes > 0:
                            return round(xframes * spf / sr, 2)
                voff = i + 4 + 32
                if voff + 18 <= size and data[voff:voff + 4] == b"VBRI":
                    vframes = struct.unpack(">I", data[voff + 14:voff + 18])[0]
                    if vframes > 0:
                        return round(vframes * spf / sr, 2)
            frames += 1
            total_dur += spf / sr
            i += flen
            continue
        i += 1
    return round(total_dur, 2) if frames >= 1 else 0.0


def _read_wav_duration(path: Path) -> float:
    """Return WAV duration in seconds when valid."""
    try:
        with wave.open(str(path), "rb") as wav_file:
            return round(wav_file.getnframes() / max(wav_file.getframerate(), 1), 2)
    except (OSError, wave.Error):
        return 0.0


def _read_flac_duration(path: Path) -> float:
    """Return FLAC duration in seconds from STREAMINFO metadata."""
    try:
        with path.open("rb") as flac_file:
            header = flac_file.read(42)
        if len(header) < 26 or header[:4] != b"fLaC" or (header[4] & 0x7F) != 0:
            return 0.0
        packed = struct.unpack(">Q", header[18:26])[0]
        sample_rate = (packed >> 44) & 0xFFFFF
        total_samples = packed & 0xFFFFFFFFF
        return round(total_samples / sample_rate, 2) if sample_rate > 0 and total_samples > 0 else 0.0
    except OSError:
        return 0.0


def _read_ogg_duration(path: Path) -> float:
    """Return OGG Vorbis/Opus duration in seconds from granule position."""
    try:
        data = path.read_bytes()
    except OSError:
        return 0.0
    sr = 0
    vorbis_idx = data.find(b"\x01vorbis")
    if vorbis_idx != -1 and vorbis_idx + 16 <= len(data):
        sr = struct.unpack("<I", data[vorbis_idx + 12:vorbis_idx + 16])[0]
    elif b"OpusHead" in data[:4096]:
        sr = 48000
    if sr <= 0:
        return 0.0
    last_page = data.rfind(b"OggS")
    if last_page == -1 or last_page + 14 > len(data):
        return 0.0
    granule = struct.unpack("<q", data[last_page + 6:last_page + 14])[0]
    return round(granule / sr, 2) if granule > 0 else 0.0


def _read_mp4_duration(path: Path) -> float:
    """Return M4A/MP4/AAC duration in seconds from the moov/mvhd box."""
    try:
        data = path.read_bytes()
    except OSError:
        return 0.0
    size = len(data)
    pos = 0
    while pos + 8 <= size:
        box_size = struct.unpack(">I", data[pos:pos + 4])[0]
        box_type = data[pos + 4:pos + 8]
        hdr = 8
        if box_size == 1 and pos + 16 <= size:
            box_size = struct.unpack(">Q", data[pos + 8:pos + 16])[0]
            hdr = 16
        elif box_size == 0:
            box_size = size - pos
        if box_size < hdr or pos + box_size > size:
            break
        if box_type == b"moov":
            sub = pos + hdr
            moov_end = pos + box_size
            while sub + 8 <= moov_end:
                s_size = struct.unpack(">I", data[sub:sub + 4])[0]
                s_type = data[sub + 4:sub + 8]
                s_hdr = 8
                if s_size == 1 and sub + 16 <= moov_end:
                    s_size = struct.unpack(">Q", data[sub + 8:sub + 16])[0]
                    s_hdr = 16
                if s_size < s_hdr or sub + s_size > moov_end:
                    break
                if s_type == b"mvhd" and sub + s_hdr + 24 <= moov_end:
                    p = sub + s_hdr
                    ver = data[p]
                    if ver == 0 and p + 20 <= moov_end:
                        timescale, dur = struct.unpack(">II", data[p + 12:p + 20])
                        return round(dur / timescale, 2) if timescale > 0 else 0.0
                    if ver == 1 and p + 32 <= moov_end:
                        timescale, dur = struct.unpack(">IQ", data[p + 20:p + 32])
                        return round(dur / timescale, 2) if timescale > 0 else 0.0
                sub += s_size
        pos += box_size
    return 0.0


def detect_audio_duration(path: Path) -> float:
    """Detect duration in seconds across supported audio formats."""
    ext = path.suffix.lower()
    if ext == ".wav":
        return _read_wav_duration(path)
    if ext == ".mp3":
        return _read_mp3_duration(path)
    if ext == ".flac":
        return _read_flac_duration(path)
    if ext == ".ogg":
        return _read_ogg_duration(path)
    if ext in {".m4a", ".mp4"}:
        return _read_mp4_duration(path)
    return 0.0


def _detect_metadata(path: Path, original_filename: str) -> tuple[str, str, float]:
    """Read MP3 embedded tags and audio duration across formats, with a filename fallback."""
    fallback_title, fallback_artist = _fallback_name(original_filename)
    title, artist = _read_id3v2(path) if path.suffix.lower() == ".mp3" else (None, None)
    duration = detect_audio_duration(path)
    return title or fallback_title, artist or fallback_artist, duration


@router.get("/songs", response_model=list[SongOut])
async def list_songs(session: SessionDep, _: UserDep, q: str | None = Query(default=None, max_length=100)) -> list[SongOut]:
    """List searchable library assets."""
    return list(await RadioRepository(session).list_songs(q))


@router.post("/songs", response_model=SongOut, status_code=201)
async def upload_song(session: SessionDep, user: UserDep, file: UploadFile = File(...), title: str | None = Form(None), artist: str | None = Form(None), genre: str | None = Form(None), duration_seconds: float | None = Form(None)) -> SongOut:
    """Store an audio upload and automatically derive its metadata when omitted."""
    if not _is_audio_file(file):
        raise HTTPException(status_code=415, detail=f"Unsupported audio file: {file.filename or 'file'}. Accepted formats: MP3, WAV, OGG, M4A, FLAC, AAC.")
    extension = Path(file.filename or "audio.bin").suffix.lower()
    destination_dir = settings.media_path
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / f"{uuid4()}{extension}"
    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=422, detail="Uploaded file is empty")
    if len(contents) > 250 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Audio uploads are limited to 250 MB")
    destination.write_bytes(contents)
    detected_title, detected_artist, detected_duration = _detect_metadata(destination, file.filename or destination.name)
    resolved_title = title.strip() if title and title.strip() else detected_title
    resolved_artist = artist.strip() if artist and artist.strip() else detected_artist

    # Check for duplicate song in library
    existing = await RadioRepository(session).find_duplicate_song(resolved_title, resolved_artist)
    if existing:
        destination.unlink(missing_ok=True)
        raise HTTPException(
            status_code=409,
            detail=f"'{resolved_title} — {resolved_artist}' is already present in the library",
        )

    try:
        song = await RadioService(session).add_song(
            payload=SongCreate(title=resolved_title, artist=resolved_artist, genre=genre, duration_seconds=duration_seconds if duration_seconds is not None and duration_seconds > 0 else detected_duration),
            file_path=str(destination),
        )
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    await RadioService(session).log("library", f"Uploaded {song.title}", user.email, {"song_id": song.id})
    return song


@router.post("/songs/batch", response_model=BatchUploadOut, status_code=201)
async def upload_songs(session: SessionDep, user: UserDep, files: list[UploadFile] = File(...)) -> BatchUploadOut:
    """Upload multiple audio files, filtering out non-audio files and skipping songs already present in library."""
    if not files:
        raise HTTPException(status_code=422, detail="Choose at least one audio file")
    valid_files = [file for file in files if _is_audio_file(file)]
    if not valid_files:
        invalid_names = [file.filename or "unnamed file" for file in files]
        raise HTTPException(
            status_code=415,
            detail=f"No valid audio files found. Skipped non-audio/shortcut file(s): {', '.join(invalid_names[:5])}. Please select MP3, WAV, OGG, M4A, FLAC, or AAC files.",
        )
    if len(valid_files) > 50:
        raise HTTPException(status_code=422, detail="Upload up to 50 audio files at a time")

    uploaded_songs: list[SongOut] = []
    duplicate_names: list[str] = []

    for file in valid_files:
        try:
            song = await upload_song(session, user, file, None, None, None, None)
            uploaded_songs.append(song)
        except HTTPException as exc:
            if exc.status_code == 409:
                # Extract clean song identifier from error detail or filename
                duplicate_names.append(file.filename or "Track")
            else:
                raise

    if not uploaded_songs and duplicate_names:
        raise HTTPException(
            status_code=409,
            detail=f"Already present in library: {', '.join(duplicate_names)}",
        )

    return BatchUploadOut(
        uploaded=uploaded_songs,
        duplicates=duplicate_names,
        count=len(uploaded_songs),
    )


@router.get("/songs/{song_id}/stream")
async def stream_song(song_id: int, session: SessionDep, _: UserDep) -> FileResponse:
    """Stream one authorized local audio asset for browser-based monitoring."""
    song = await RadioRepository(session).get_song(song_id)
    if not song:
        raise HTTPException(status_code=404, detail="Song not found")
    path = Path(song.file_path).resolve()
    if not path.is_file() or settings.media_path not in path.parents:
        raise HTTPException(status_code=404, detail="Audio file is unavailable")
    return FileResponse(path, media_type=None, filename=path.name)


@router.delete("/songs", status_code=200)
async def delete_all_songs(session: SessionDep, user: UserDep) -> dict[str, int]:
    """Delete all library songs, clean up local files, and clear the live queue."""
    repository = RadioRepository(session)
    songs = await repository.list_songs()
    for song in songs:
        path = Path(song.file_path)
        if path.is_file() and settings.media_path in path.resolve().parents:
            path.unlink(missing_ok=True)
    count = await repository.delete_all_songs()
    await RadioService(session).clear_queue(actor=user.email)
    await RadioService(session).log("library", f"Deleted all {count} songs", user.email, {"count": count})
    return {"deleted": count}


@router.delete("/songs/{song_id}", status_code=204)
async def delete_song(song_id: int, session: SessionDep, user: UserDep) -> None:
    """Delete a library record and its stored file when owned by local media."""
    repository = RadioRepository(session)
    song = await repository.get_song(song_id)
    if not song:
        raise HTTPException(status_code=404, detail="Song not found")
    path = Path(song.file_path)
    await repository.delete_song(song)
    if path.is_file() and settings.media_path in path.resolve().parents:
        path.unlink(missing_ok=True)
    await RadioService(session).log("library", f"Deleted {song.title}", user.email, {"song_id": song_id})
