"""Recovery policy for faults reported by monitoring and service boundaries."""

from __future__ import annotations

import logging
from collections.abc import Iterable

from autopilot.autopilot_events import AutopilotEvent, AutopilotEventType
from autopilot.autopilot_state import ActionType, AutopilotAction, MediaRef, StationState
from autopilot.event_bus import EventBus
from autopilot.queue_manager import QueueManager

logger = logging.getLogger(__name__)


class RecoveryManager:
    """Create auditable recovery actions without attempting media execution."""

    def __init__(self, queue_manager: QueueManager, event_bus: EventBus) -> None:
        self._queue_manager = queue_manager
        self._event_bus = event_bus

    async def recover(self, state: StationState, candidates: Iterable[MediaRef], reason: str) -> AutopilotAction:
        """Choose a replacement/reload action and emit recovery observability events."""
        action = self._queue_manager.replacement_action(state, candidates)
        if action.action_type is ActionType.NO_ACTION:
            action = AutopilotAction(ActionType.RECOVER_PLAYBACK, "Reload queue after playback fault", {"reason": reason}, priority=5)
        await self._event_bus.publish(AutopilotEvent(AutopilotEventType.ERROR_OCCURRED, {"error": reason, "recovery_action": action.to_dict()}, source="recovery_manager", correlation_id=action.correlation_id))
        logger.warning("Autopilot recovery decision created", extra={"action": action.action_type.value, "reason": reason, "correlation_id": action.correlation_id})
        return action
