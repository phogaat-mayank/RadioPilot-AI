"""Song library endpoints."""

from pathlib import Path
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


@router.get("/songs", response_model=list[SongOut])
async def list_songs(session: SessionDep, _: UserDep, q: str | None = Query(default=None, max_length=100)) -> list[SongOut]:
    """List searchable library assets."""
    return list(await RadioRepository(session).list_songs(q))


@router.post("/songs", response_model=SongOut, status_code=201)
async def upload_song(session: SessionDep, user: UserDep, file: UploadFile = File(...), title: str = Form(...), artist: str = Form("Unknown Artist"), genre: str | None = Form(None), duration_seconds: float = Form(0)) -> SongOut:
    """Store an audio upload and register its metadata."""
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
    song = await RadioService(session).add_song(
        payload=SongCreate(title=title, artist=artist, genre=genre, duration_seconds=duration_seconds),
        file_path=str(destination),
    )
    await RadioService(session).log("library", f"Uploaded {song.title}", user.email, {"song_id": song.id})
    return song


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
