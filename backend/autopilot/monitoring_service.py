"""Playback health observation that emits events but never performs playback."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timezone
import logging

from autopilot.autopilot_events import AutopilotEvent, AutopilotEventType
from autopilot.autopilot_state import MediaRef, SystemHealth
from autopilot.event_bus import EventBus

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class PlaybackObservation:
    """Minimal playback data supplied by an existing backend service."""

    status: str
    current_song: MediaRef | None
    queue_depth: int
    playback_position: float
    observed_at: datetime


PlaybackProbe = Callable[[], Awaitable[PlaybackObservation]]


class MonitoringService:
    """Detect state transitions, idle playback, and missing media assets."""

    def __init__(self, probe: PlaybackProbe, event_bus: EventBus, idle_threshold_seconds: float = 20.0) -> None:
        self._probe = probe
        self._event_bus = event_bus
        self._idle_threshold = idle_threshold_seconds
        self._previous_song_id: int | None = None
        self._previous_status = "stopped"
        self._last_position = 0.0
        self._last_progress_at = datetime.now(timezone.utc)

    async def poll(self) -> tuple[PlaybackObservation, SystemHealth]:
        """Observe once and publish relevant lifecycle or error events."""
        try:
            observation = await self._probe()
        except Exception as error:
            logger.exception("Autopilot playback probe failed")
            await self._event_bus.publish(AutopilotEvent(AutopilotEventType.ERROR_OCCURRED, {"error": str(error), "component": "monitoring"}, source="monitoring_service"))
            now = datetime.now(timezone.utc)
            return PlaybackObservation("unknown", None, 0, 0.0, now), SystemHealth(playback_healthy=False, media_healthy=True, last_error=str(error))

        now = observation.observed_at
        current_id = observation.current_song.id if observation.current_song else None
        if current_id != self._previous_song_id:
            if self._previous_song_id is not None:
                await self._event_bus.publish(AutopilotEvent(AutopilotEventType.SONG_FINISHED, {"song_id": self._previous_song_id}, source="monitoring_service"))
            if current_id is not None:
                await self._event_bus.publish(AutopilotEvent(AutopilotEventType.SONG_STARTED, {"song_id": current_id}, source="monitoring_service"))
            self._previous_song_id = current_id
            self._last_position = observation.playback_position
            self._last_progress_at = now
        if observation.status == "playing" and observation.playback_position > self._last_position:
            self._last_position = observation.playback_position
            self._last_progress_at = now
        idle_seconds = max(0.0, (now - self._last_progress_at).total_seconds()) if observation.status == "playing" else 0.0
        media_healthy = observation.current_song is None or observation.current_song.available
        playback_healthy = observation.status != "playing" or idle_seconds < self._idle_threshold
        if observation.queue_depth == 0 and observation.status != "playing":
            await self._event_bus.publish(AutopilotEvent(AutopilotEventType.QUEUE_EMPTY, source="monitoring_service"))
        if not media_healthy or not playback_healthy:
            message = "Current media is unavailable" if not media_healthy else "Playback position is not progressing"
            await self._event_bus.publish(AutopilotEvent(AutopilotEventType.ERROR_OCCURRED, {"error": message, "idle_seconds": idle_seconds, "component": "monitoring"}, source="monitoring_service"))
        self._previous_status = observation.status
        return observation, SystemHealth(playback_healthy=playback_healthy, media_healthy=media_healthy, idle_seconds=idle_seconds, last_error=None if playback_healthy and media_healthy else "Playback monitoring detected a fault")
