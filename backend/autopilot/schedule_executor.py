"""Schedule polling and event emission for autopilot policy."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable
from datetime import datetime, timezone
import logging

from autopilot.autopilot_events import AutopilotEvent, AutopilotEventType
from autopilot.autopilot_state import ScheduleRef
from autopilot.event_bus import EventBus

logger = logging.getLogger(__name__)
ScheduleProvider = Callable[[], Awaitable[Iterable[ScheduleRef]]]


class ScheduleExecutor:
    """Reads due schedules and emits events; execution remains outside this class."""

    def __init__(self, provider: ScheduleProvider, event_bus: EventBus, misfire_grace_seconds: float = 300.0) -> None:
        if misfire_grace_seconds < 0:
            raise ValueError("misfire_grace_seconds cannot be negative")
        self._provider = provider
        self._event_bus = event_bus
        self._misfire_grace_seconds = misfire_grace_seconds
        self._triggered: set[int] = set()

    async def poll(self, now: datetime | None = None) -> tuple[ScheduleRef, ...]:
        """Publish one SCHEDULE_TRIGGERED event per newly due schedule entry."""
        current = now or datetime.now(timezone.utc)
        due: list[ScheduleRef] = []
        for entry in await self._provider():
            age_seconds = (current - entry.run_at).total_seconds()
            if not entry.enabled or entry.id in self._triggered or entry.run_at > current or age_seconds > self._misfire_grace_seconds:
                continue
            self._triggered.add(entry.id)
            due.append(entry)
            await self._event_bus.publish(AutopilotEvent(AutopilotEventType.SCHEDULE_TRIGGERED, {"schedule_id": entry.id, "event_type": entry.event_type, "playlist_id": entry.playlist_id, **dict(entry.payload)}, source="schedule_executor"))
            logger.info("Autopilot schedule became due", extra={"schedule_id": entry.id, "event_type": entry.event_type})
        return tuple(due)

    def mark_pending(self, schedule_id: int) -> None:
        """Allow a corrected or rescheduled entry to be evaluated again."""
        self._triggered.discard(schedule_id)
