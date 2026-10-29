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
