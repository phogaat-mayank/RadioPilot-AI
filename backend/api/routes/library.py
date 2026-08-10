"""Song library endpoints."""

from pathlib import Path
import re
import wave
from uuid import uuid4
from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse

from api.deps import SessionDep, UserDep
from core.config import settings
from repositories.radio import RadioRepository
from schemas.radio import SongCreate, SongOut
from services.radio import RadioService

router = APIRouter(prefix="/library", tags=["library"])
_allowed_content_types = {"audio/mpeg", "audio/wav", "audio/ogg", "audio/mp4", "audio/x-wav"}


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


def _read_wav_duration(path: Path) -> float:
    """Return WAV duration when available; compressed formats safely fall back to zero."""
    try:
        with wave.open(str(path), "rb") as wav_file:
            return wav_file.getnframes() / max(wav_file.getframerate(), 1)
    except (OSError, wave.Error):
        return 0.0


def _detect_metadata(path: Path, original_filename: str) -> tuple[str, str, float]:
    """Read MP3 embedded tags and WAV duration, with a filename fallback for all formats."""
    fallback_title, fallback_artist = _fallback_name(original_filename)
    title, artist = _read_id3v2(path) if path.suffix.lower() == ".mp3" else (None, None)
    duration = _read_wav_duration(path) if path.suffix.lower() == ".wav" else 0.0
    return title or fallback_title, artist or fallback_artist, duration


@router.get("/songs", response_model=list[SongOut])
async def list_songs(session: SessionDep, _: UserDep, q: str | None = Query(default=None, max_length=100)) -> list[SongOut]:
    """List searchable library assets."""
    return list(await RadioRepository(session).list_songs(q))


@router.post("/songs", response_model=SongOut, status_code=201)
async def upload_song(session: SessionDep, user: UserDep, file: UploadFile = File(...), title: str | None = Form(None), artist: str | None = Form(None), genre: str | None = Form(None), duration_seconds: float | None = Form(None)) -> SongOut:
    """Store an audio upload and automatically derive its metadata when omitted."""
    if file.content_type not in _allowed_content_types:
        raise HTTPException(status_code=415, detail="Only common audio formats are accepted")
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
    try:
        song = await RadioService(session).add_song(
            payload=SongCreate(title=title.strip() if title and title.strip() else detected_title, artist=artist.strip() if artist and artist.strip() else detected_artist, genre=genre, duration_seconds=duration_seconds if duration_seconds is not None and duration_seconds > 0 else detected_duration),
            file_path=str(destination),
        )
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    await RadioService(session).log("library", f"Uploaded {song.title}", user.email, {"song_id": song.id})
    return song


@router.post("/songs/batch", response_model=list[SongOut], status_code=201)
async def upload_songs(session: SessionDep, user: UserDep, files: list[UploadFile] = File(...)) -> list[SongOut]:
    """Upload multiple audio files and detect each file's metadata independently."""
    if not files:
        raise HTTPException(status_code=422, detail="Choose at least one audio file")
    if len(files) > 50:
        raise HTTPException(status_code=422, detail="Upload up to 50 audio files at a time")
    invalid = [file.filename or "unnamed file" for file in files if file.content_type not in _allowed_content_types]
    if invalid:
        raise HTTPException(status_code=415, detail=f"Unsupported audio file(s): {', '.join(invalid)}")
    return [await upload_song(session, user, file, None, None, None, None) for file in files]


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
