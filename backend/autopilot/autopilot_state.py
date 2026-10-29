"""Typed, serializable state and action contracts for decision-only autopilot."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Mapping
from uuid import uuid4


class ActionType(StrEnum):
    """Actions that backend services may execute after an autopilot decision."""

    PLAY_PLAYLIST = "PLAY_PLAYLIST"
    PLAY_ADS = "PLAY_ADS"
    PLAY_JINGLE = "PLAY_JINGLE"
    PREPARE_NEWS = "PREPARE_NEWS"
    PLAY_NEWS = "PLAY_NEWS"
    LOAD_QUEUE = "LOAD_QUEUE"
    START_LIVE = "START_LIVE"
    END_LIVE = "END_LIVE"
    RECOVER_PLAYBACK = "RECOVER_PLAYBACK"
    SKIP_TRACK = "SKIP_TRACK"
    NO_ACTION = "NO_ACTION"


@dataclass(frozen=True, slots=True)
class MediaRef:
    """A media reference safe to pass between policy and service layers."""

    id: int
    title: str
    artist: str = "Unknown Artist"
    duration_seconds: float = 0.0
    available: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "title": self.title, "artist": self.artist, "duration_seconds": self.duration_seconds, "available": self.available}

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "MediaRef":
        return cls(id=int(value["id"]), title=str(value["title"]), artist=str(value.get("artist", "Unknown Artist")), duration_seconds=float(value.get("duration_seconds", 0)), available=bool(value.get("available", True)))


@dataclass(frozen=True, slots=True)
class ScheduleRef:
    """A due-or-upcoming schedule entry supplied by the scheduler service."""

    id: int
    event_type: str
    run_at: datetime
    playlist_id: int | None = None
    payload: Mapping[str, Any] = field(default_factory=dict)
    enabled: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "event_type": self.event_type, "run_at": self.run_at.isoformat(), "playlist_id": self.playlist_id, "payload": dict(self.payload), "enabled": self.enabled}

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ScheduleRef":
        return cls(id=int(value["id"]), event_type=str(value["event_type"]), run_at=datetime.fromisoformat(str(value["run_at"])), playlist_id=value.get("playlist_id"), payload=dict(value.get("payload", {})), enabled=bool(value.get("enabled", True)))


@dataclass(frozen=True, slots=True)
class SystemHealth:
    """Health observations used for policy; no engine handles are stored here."""

    playback_healthy: bool = True
    media_healthy: bool = True
    idle_seconds: float = 0.0
    last_error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"playback_healthy": self.playback_healthy, "media_healthy": self.media_healthy, "idle_seconds": self.idle_seconds, "last_error": self.last_error}

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "SystemHealth":
        return cls(playback_healthy=bool(value.get("playback_healthy", True)), media_healthy=bool(value.get("media_healthy", True)), idle_seconds=float(value.get("idle_seconds", 0)), last_error=value.get("last_error"))


@dataclass(frozen=True, slots=True)
class StationState:
    """Shared station snapshot consumed by all autopilot decision components."""

    current_song: MediaRef | None = None
    current_playlist: int | None = None
    queue: tuple[MediaRef, ...] = ()
    playback_position: float = 0.0
    current_mode: str = "MANUAL"
    autopilot_enabled: bool = False
    manual_override: bool = False
    live_mode: bool = False
    mic_enabled: bool = False
    ads_due: bool = False
    schedule: tuple[ScheduleRef, ...] = ()
    system_health: SystemHealth = field(default_factory=SystemHealth)
    last_event: str | None = None
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def evolve(self, **changes: Any) -> "StationState":
        """Return a timestamped immutable update."""
        return replace(self, **changes, updated_at=datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        return {"current_song": self.current_song.to_dict() if self.current_song else None, "current_playlist": self.current_playlist, "queue": [song.to_dict() for song in self.queue], "playback_position": self.playback_position, "current_mode": self.current_mode, "autopilot_enabled": self.autopilot_enabled, "manual_override": self.manual_override, "live_mode": self.live_mode, "mic_enabled": self.mic_enabled, "ads_due": self.ads_due, "schedule": [entry.to_dict() for entry in self.schedule], "system_health": self.system_health.to_dict(), "last_event": self.last_event, "updated_at": self.updated_at.isoformat()}

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "StationState":
        current = value.get("current_song")
        return cls(current_song=MediaRef.from_dict(current) if current else None, current_playlist=value.get("current_playlist"), queue=tuple(MediaRef.from_dict(item) for item in value.get("queue", [])), playback_position=float(value.get("playback_position", 0)), current_mode=str(value.get("current_mode", "MANUAL")), autopilot_enabled=bool(value.get("autopilot_enabled", False)), manual_override=bool(value.get("manual_override", False)), live_mode=bool(value.get("live_mode", False)), mic_enabled=bool(value.get("mic_enabled", False)), ads_due=bool(value.get("ads_due", False)), schedule=tuple(ScheduleRef.from_dict(item) for item in value.get("schedule", [])), system_health=SystemHealth.from_dict(value.get("system_health", {})), last_event=value.get("last_event"), updated_at=datetime.fromisoformat(str(value.get("updated_at", datetime.now(timezone.utc).isoformat()))))


@dataclass(frozen=True, slots=True)
class AutopilotAction:
    """A validated instruction for the backend service execution boundary."""

    action_type: ActionType
    reason: str
    payload: Mapping[str, Any] = field(default_factory=dict)
    priority: int = 100
    correlation_id: str = field(default_factory=lambda: str(uuid4()))
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def is_noop(self) -> bool:
        return self.action_type is ActionType.NO_ACTION

    def to_dict(self) -> dict[str, Any]:
        return {"action_type": self.action_type.value, "reason": self.reason, "payload": dict(self.payload), "priority": self.priority, "correlation_id": self.correlation_id, "created_at": self.created_at.isoformat()}
