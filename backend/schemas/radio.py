"""Typed request and response contracts."""

from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict, Field


class TokenPair(BaseModel):
    """Short-lived access and refresh credentials."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class LoginRequest(BaseModel):
    """Credential login payload."""
    email: str
    password: str = Field(min_length=8)


class SongCreate(BaseModel):
    """Song metadata payload."""
    title: str = Field(min_length=1, max_length=255)
    artist: str = Field(default="Unknown Artist", max_length=255)
    album: Optional[str] = None
    genre: Optional[str] = None
    duration_seconds: float = Field(default=0, ge=0)


class SongOut(SongCreate):
    """Serialized audio asset."""
    model_config = ConfigDict(from_attributes=True)
    id: int
    file_path: str


class PlaylistCreate(BaseModel):
    """Playlist create payload."""
    name: str = Field(min_length=1, max_length=255)
    description: Optional[str] = None
    repeat_enabled: bool = False
    shuffle_enabled: bool = False


class PlaylistOut(PlaylistCreate):
    """Serialized playlist summary."""
    model_config = ConfigDict(from_attributes=True)
    id: int


class ReorderPlaylist(BaseModel):
    """Drag-and-drop ordering payload."""
    song_ids: list[int] = Field(min_length=1)


class ScheduleCreate(BaseModel):
    """One-time scheduler payload."""
    name: str
    event_type: Literal["playlist", "advertisement", "jingle", "announcement", "news", "weather", "show"] = "playlist"
    playlist_id: Optional[int] = None
    run_at: datetime
    enabled: bool = True


class ScheduleOut(ScheduleCreate):
    """Serialized schedule."""
    model_config = ConfigDict(from_attributes=True)
    id: int


class ModeChange(BaseModel):
    """Station mode change request."""
    mode: Literal["AUTOPILOT", "MANUAL"]


class VolumeChange(BaseModel):
    """Volume request."""
    volume: int = Field(ge=0, le=100)


class QueueSong(BaseModel):
    """Queue insertion request."""
    song_id: int


class TrackEnded(BaseModel):
    """Browser playback completion token used to prevent duplicate advances."""
    playback_revision: int = Field(ge=1)


class PlaybackState(BaseModel):
    """Real-time playback state safe for client display."""
    status: str
    mode: str
    volume: int
    current_song: Optional[SongOut] = None
    current_position_seconds: float
    playback_revision: int = 0
    queue: list[SongOut]
    updated_at: datetime
