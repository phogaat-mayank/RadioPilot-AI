"""Playlist CRUD and ordering endpoints."""

from fastapi import APIRouter, HTTPException
from api.deps import SessionDep, UserDep
from models.entities import Playlist
from repositories.radio import RadioRepository
from schemas.radio import PlaylistCreate, PlaylistDetail, PlaylistOut, ReorderPlaylist, SongOut
from services.radio import RadioService

router = APIRouter(prefix="/playlists", tags=["playlists"])


@router.get("", response_model=list[PlaylistOut])
async def list_playlists(session: SessionDep, _: UserDep) -> list[Playlist]:
    """Return all station playlists."""
    return list(await RadioRepository(session).list_playlists())


@router.post("", response_model=PlaylistOut, status_code=201)
async def create_playlist(payload: PlaylistCreate, session: SessionDep, user: UserDep) -> Playlist:
    """Create a playlist."""
    playlist = await RadioService(session).create_playlist(payload)
    await RadioService(session).log("playlist", f"Created {playlist.name}", user.email)
    return playlist


@router.get("/{playlist_id}", response_model=PlaylistDetail)
async def get_playlist(playlist_id: int, session: SessionDep, _: UserDep) -> PlaylistDetail:
    """Return a playlist and its current ordered songs for dashboard management."""
    playlist = await RadioRepository(session).get_playlist(playlist_id)
    if not playlist:
        raise HTTPException(status_code=404, detail="Playlist not found")
    return PlaylistDetail.model_validate(playlist, from_attributes=True).model_copy(update={"songs": [SongOut.model_validate(item.song, from_attributes=True) for item in playlist.items]})


@router.post("/{playlist_id}/songs/{song_id}", status_code=204)
async def add_song(playlist_id: int, song_id: int, session: SessionDep, _: UserDep) -> None:
    """Append a library asset to a playlist."""
    repository = RadioRepository(session)
    playlist, song = await repository.get_playlist(playlist_id), await repository.get_song(song_id)
    if not playlist or not song:
        raise HTTPException(status_code=404, detail="Playlist or song not found")
    await repository.add_to_playlist(playlist, song)


@router.post("/{playlist_id}/play", status_code=200)
async def play_playlist(playlist_id: int, session: SessionDep, user: UserDep) -> dict:
    """Queue an entire playlist and begin it through the playback controller."""
    try:
        state = await RadioService(session).run_playlist(playlist_id, user.email)
        return state.model_dump(mode="json")
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.put("/{playlist_id}/order", status_code=204)
async def reorder(playlist_id: int, payload: ReorderPlaylist, session: SessionDep, _: UserDep) -> None:
    """Persist drag-and-drop playlist ordering."""
    repository = RadioRepository(session)
    playlist = await repository.get_playlist(playlist_id)
    if not playlist:
        raise HTTPException(status_code=404, detail="Playlist not found")
    try:
        await repository.reorder_playlist(playlist, payload.song_ids)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
