"""SQLAlchemy entities for radio operations."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional
from sqlalchemy import Boolean, DateTime, Enum as SqlEnum, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all ORM entities."""


class StationMode(str, Enum):
    """Station control modes."""

    AUTOPILOT = "AUTOPILOT"
    MANUAL = "MANUAL"


class UserRole(str, Enum):
    """Application roles."""

    ADMIN = "admin"
    RJ = "rj"
    VIEWER = "viewer"
    PRODUCER = "producer"
    GUEST = "guest"


class User(Base):
    """Authenticated dashboard user."""

    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(SqlEnum(UserRole), default=UserRole.RJ)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Song(Base):
    """Audio asset available to the station."""

    __tablename__ = "songs"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(255), index=True)
    artist: Mapped[str] = mapped_column(String(255), default="Unknown Artist")
    album: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    genre: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    duration_seconds: Mapped[float] = mapped_column(Float, default=0)
    file_path: Mapped[str] = mapped_column(String(1024), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Playlist(Base):
    """Ordered collection of songs."""

    __tablename__ = "playlists"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    repeat_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    shuffle_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    items: Mapped[list[PlaylistSong]] = relationship(back_populates="playlist", cascade="all, delete-orphan", order_by="PlaylistSong.position")


class PlaylistSong(Base):
    """Playlist ordering record."""

    __tablename__ = "playlist_songs"
    __table_args__ = (UniqueConstraint("playlist_id", "song_id", name="uq_playlist_song"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    playlist_id: Mapped[int] = mapped_column(ForeignKey("playlists.id", ondelete="CASCADE"))
    song_id: Mapped[int] = mapped_column(ForeignKey("songs.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(Integer)
    playlist: Mapped[Playlist] = relationship(back_populates="items")
    song: Mapped[Song] = relationship()


class Schedule(Base):
    """Persisted scheduled playlist or event."""

    __tablename__ = "schedules"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    event_type: Mapped[str] = mapped_column(String(50), default="playlist")
    playlist_id: Mapped[Optional[int]] = mapped_column(ForeignKey("playlists.id"), nullable=True)
    run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)


class Advertisement(Base):
    """Advertiser audio inventory with availability controls."""

    __tablename__ = "advertisements"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    file_path: Mapped[str] = mapped_column(String(1024), unique=True)
    duration_seconds: Mapped[float] = mapped_column(Float, default=0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PlaybackHistory(Base):
    """Immutable playback audit record."""

    __tablename__ = "playback_history"
    id: Mapped[int] = mapped_column(primary_key=True)
    song_id: Mapped[Optional[int]] = mapped_column(ForeignKey("songs.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(50))
    position_seconds: Mapped[float] = mapped_column(Float, default=0)
    performed_by: Mapped[str] = mapped_column(String(255), default="system")
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SystemState(Base):
    """Singleton persistent station state."""

    __tablename__ = "system_state"
    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    mode: Mapped[StationMode] = mapped_column(SqlEnum(StationMode), default=StationMode.MANUAL)
    volume: Mapped[int] = mapped_column(Integer, default=75)
    emergency_active: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class AuditLog(Base):
    """Security and operations audit log."""

    __tablename__ = "logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    category: Mapped[str] = mapped_column(String(80), index=True)
    level: Mapped[str] = mapped_column(String(20), default="INFO")
    message: Mapped[str] = mapped_column(Text)
    actor: Mapped[str] = mapped_column(String(255), default="system")
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Notification(Base):
    """Operator-facing operational notification."""

    __tablename__ = "notifications"
    id: Mapped[int] = mapped_column(primary_key=True)
    severity: Mapped[str] = mapped_column(String(20), default="info")
    message: Mapped[str] = mapped_column(Text)
    read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AITask(Base):
    """Traceable unit of AI work requested by an operator or autopilot."""

    __tablename__ = "ai_tasks"
    id: Mapped[int] = mapped_column(primary_key=True)
    task_type: Mapped[str] = mapped_column(String(80), index=True)
    status: Mapped[str] = mapped_column(String(30), default="queued", index=True)
    agent_name: Mapped[str] = mapped_column(String(80))
    requested_by: Mapped[str] = mapped_column(String(255), default="system")
    input_json: Mapped[dict] = mapped_column(JSON, default=dict)
    output_json: Mapped[dict] = mapped_column(JSON, default=dict)
    model: Mapped[str] = mapped_column(String(120), default="deterministic")
    execution_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class AILog(Base):
    """Detailed AI observability event independent of station audit logs."""

    __tablename__ = "ai_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[Optional[int]] = mapped_column(ForeignKey("ai_tasks.id"), nullable=True, index=True)
    level: Mapped[str] = mapped_column(String(20), default="INFO")
    message: Mapped[str] = mapped_column(Text)
    agent_name: Mapped[str] = mapped_column(String(80), default="supervisor")
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AIMemory(Base):
    """Long-lived, namespaced AI memory with unique semantic keys."""

    __tablename__ = "ai_memory"
    __table_args__ = (UniqueConstraint("namespace", "memory_key", name="uq_ai_memory_key"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    namespace: Mapped[str] = mapped_column(String(80), index=True)
    memory_key: Mapped[str] = mapped_column(String(255))
    value_json: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class AIConversation(Base):
    """Ordered exchange within an RJ AI chat session."""

    __tablename__ = "ai_conversations"
    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[str] = mapped_column(String(80), index=True)
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AIDecision(Base):
    """An AI recommendation requiring optional RJ approval."""

    __tablename__ = "ai_decisions"
    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[Optional[int]] = mapped_column(ForeignKey("ai_tasks.id"), nullable=True, index=True)
    decision_type: Mapped[str] = mapped_column(String(80))
    decision_json: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(30), default="proposed", index=True)
    approved_by: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AIDJSettings(Base):
    """Singleton persistent AI DJ voice engine configuration."""

    __tablename__ = "ai_dj_settings"
    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    voice_id: Mapped[str] = mapped_column(String(100), default="hi_IN-priyamvada-medium")
    language: Mapped[str] = mapped_column(String(10), default="hi")
    frequency: Mapped[int] = mapped_column(Integer, default=1)
    volume: Mapped[int] = mapped_column(Integer, default=100)
    intro_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    outro_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    greeting_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
