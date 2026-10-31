"""Typed request and response contracts."""

from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict, Field


class TokenPair(BaseModel):
    """Short-lived access and refresh credentials."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshTokenRequest(BaseModel):
    """Refresh token payload."""
    refresh_token: str


class UserOut(BaseModel):
    """Serialized user representation."""
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: str
    role: str
    is_active: bool


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


class BatchUploadOut(BaseModel):
    """Bulk song upload result including skipped duplicates."""
    uploaded: list[SongOut] = []
    duplicates: list[str] = []
    count: int = 0


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


class PlaylistDetail(PlaylistOut):
    """A playlist with its ordered, currently available library songs."""

    songs: list[SongOut] = []


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
    metadata_json: dict = Field(default_factory=dict)


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


class AnnouncementEnded(BaseModel):
    """Browser completion payload when an AI DJ announcement finishes."""
    announcement_id: str | None = None
    playback_revision: int | None = None


class AnnouncementOut(BaseModel):
    """Spoken AI DJ announcement payload for the player."""
    id: str
    text: str
    voice_id: str
    duration_seconds: float
    stream_url: str
    announcement_type: str = "intro"


class PlaybackState(BaseModel):
    """Real-time playback state safe for client display."""
    status: str
    mode: str
    volume: int
    current_song: Optional[SongOut] = None
    active_announcement: Optional[AnnouncementOut] = None
    current_position_seconds: float
    playback_revision: int = 0
    queue: list[SongOut]
    updated_at: datetime


class AIDJSettingsOut(BaseModel):
    """AI DJ Voice Engine configuration."""
    model_config = ConfigDict(from_attributes=True)
    enabled: bool = True
    voice_id: str = "hi_IN-priyamvada-medium"
    language: str = "hi"
    frequency: int = 1
    volume: int = 100
    intro_enabled: bool = True
    outro_enabled: bool = False
    greeting_enabled: bool = True


class AIDJSettingsUpdate(BaseModel):
    """Update payload for AI DJ Voice Engine configuration."""
    enabled: Optional[bool] = None
    voice_id: Optional[str] = None
    language: Optional[str] = None
    frequency: Optional[int] = Field(default=None, ge=1, le=10)
    volume: Optional[int] = Field(default=None, ge=0, le=100)
    intro_enabled: Optional[bool] = None
    outro_enabled: Optional[bool] = None
    greeting_enabled: Optional[bool] = None


class TTSVoiceOut(BaseModel):
    """Metadata for verified Piper neural voice models."""
    id: str
    name: str
    language: str
    language_code: str
    gender: str
    quality: str
    sample_rate: int = 22050
    downloaded: bool = True
    license: str


class TTSSynthesizeRequest(BaseModel):
    """Synthesize arbitrary announcement text request."""
    text: str = Field(min_length=1, max_length=2000)
    voice_id: Optional[str] = None


class ManualAnnouncementRequest(BaseModel):
    """Manual announcement broadcast request."""
    text: str = Field(min_length=1, max_length=2000)
    voice_id: Optional[str] = None
    language: Optional[str] = None
    play_now: bool = False
    play_immediately: Optional[bool] = None

    @property
    def should_play_now(self) -> bool:
        if self.play_immediately is not None:
            return self.play_immediately
        return self.play_now
