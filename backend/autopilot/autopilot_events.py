"""Event contracts for the decoupled autopilot event bus."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Mapping
from uuid import uuid4


class AutopilotEventType(StrEnum):
    SONG_STARTED = "SONG_STARTED"
    SONG_FINISHED = "SONG_FINISHED"
    QUEUE_EMPTY = "QUEUE_EMPTY"
    SCHEDULE_TRIGGERED = "SCHEDULE_TRIGGERED"
    MANUAL_MODE_ENABLED = "MANUAL_MODE_ENABLED"
    AUTOPILOT_ENABLED = "AUTOPILOT_ENABLED"
    AUTOPILOT_DISABLED = "AUTOPILOT_DISABLED"
    LIVE_MODE_STARTED = "LIVE_MODE_STARTED"
    LIVE_MODE_ENDED = "LIVE_MODE_ENDED"
    ERROR_OCCURRED = "ERROR_OCCURRED"


@dataclass(frozen=True, slots=True)
class AutopilotEvent:
    """Immutable event with an observability-friendly correlation id."""

    event_type: AutopilotEventType
    payload: Mapping[str, Any] = field(default_factory=dict)
    source: str = "autopilot"
    occurred_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    correlation_id: str = field(default_factory=lambda: str(uuid4()))
