"""Lifecycle coordinator for the decision-only Autopilot subsystem."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import datetime, timedelta, timezone
from collections.abc import Awaitable, Callable, Iterable

from autopilot.autopilot_events import AutopilotEvent, AutopilotEventType
from autopilot.autopilot_state import ActionType, AutopilotAction, MediaRef, StationState
from autopilot.decision_engine import DecisionEngine
from autopilot.event_bus import EventBus
from autopilot.monitoring_service import MonitoringService
from autopilot.queue_manager import QueueManager
from autopilot.recovery_manager import RecoveryManager
from autopilot.schedule_executor import ScheduleExecutor
from autopilot.state_manager import StateManager

logger = logging.getLogger(__name__)
ActionExecutor = Callable[[AutopilotAction], Awaitable[None]]
StateProvider = Callable[[], Awaitable[StationState]]
MediaProvider = Callable[[], Awaitable[Iterable[MediaRef]]]


class AutopilotManager:
    """Coordinate monitors and decisions while delegating all execution to services."""

    def __init__(self, *, state_manager: StateManager, decision_engine: DecisionEngine, event_bus: EventBus, queue_manager: QueueManager, schedule_executor: ScheduleExecutor, monitoring_service: MonitoringService, recovery_manager: RecoveryManager, state_provider: StateProvider, media_provider: MediaProvider, action_executor: ActionExecutor, interval_seconds: float = 2.0) -> None:
        if interval_seconds <= 0:
            raise ValueError("interval_seconds must be positive")
        self._state_manager = state_manager
        self._decision_engine = decision_engine
        self._event_bus = event_bus
        self._queue_manager = queue_manager
        self._schedule_executor = schedule_executor
        self._monitoring_service = monitoring_service
        self._recovery_manager = recovery_manager
        self._state_provider = state_provider
        self._media_provider = media_provider
        self._action_executor = action_executor
        self._interval_seconds = interval_seconds
        self._task: asyncio.Task[None] | None = None
        self._subscriptions: list[tuple[AutopilotEventType, str]] = []
        self._lifecycle_lock = asyncio.Lock()
        self._last_recovery_at: datetime | None = None

    @property
    def running(self) -> bool:
        """Return whether the monitoring loop currently owns a task."""
        return self._task is not None and not self._task.done()

    async def start(self) -> None:
        """Enable decision making and begin the monitoring loop exactly once."""
        async with self._lifecycle_lock:
            if self.running:
                return
            await self._state_manager.restore()
            await self._state_manager.update(lambda state: state.evolve(autopilot_enabled=True, manual_override=False, current_mode="AUTOPILOT"))
            await self._subscribe()
            self._task = asyncio.create_task(self._monitor_loop(), name="radiopilot-autopilot")
        await self._event_bus.publish(AutopilotEvent(AutopilotEventType.AUTOPILOT_ENABLED, source="autopilot_manager"))
        logger.info("Autopilot manager started")

    async def stop(self, manual_override: bool = True) -> None:
        """Stop monitoring and persist a manual-safe state."""
        async with self._lifecycle_lock:
            task, self._task = self._task, None
            if task:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
            await self._unsubscribe()
            await self._state_manager.update(lambda state: state.evolve(autopilot_enabled=False, manual_override=manual_override, current_mode="MANUAL" if manual_override else state.current_mode))
            await self._state_manager.save()
        event_type = AutopilotEventType.MANUAL_MODE_ENABLED if manual_override else AutopilotEventType.AUTOPILOT_DISABLED
        await self._event_bus.publish(AutopilotEvent(event_type, source="autopilot_manager"))
        logger.info("Autopilot manager stopped", extra={"manual_override": manual_override})

    async def run_once(self) -> AutopilotAction:
        """Refresh state, poll monitors/schedules, and dispatch one service action."""
        external = await self._state_provider()
        current = await self._state_manager.snapshot()
        state = external.evolve(autopilot_enabled=current.autopilot_enabled, manual_override=current.manual_override, current_mode=current.current_mode, last_event=current.last_event)
        observation, health = await self._monitoring_service.poll()
        state = state.evolve(current_song=observation.current_song, playback_position=observation.playback_position, system_health=health)
        await self._state_manager.replace(state)
        await self._schedule_executor.poll()
        action = self._decision_engine.decide(await self._state_manager.snapshot())
        await self._dispatch(action)
        return action

    async def _monitor_loop(self) -> None:
        while True:
            try:
                await self.run_once()
            except asyncio.CancelledError:
                raise
            except Exception as error:
                logger.exception("Autopilot monitoring loop failed")
                await self._event_bus.publish(AutopilotEvent(AutopilotEventType.ERROR_OCCURRED, {"error": str(error), "component": "autopilot_manager"}, source="autopilot_manager"))
            await asyncio.sleep(self._interval_seconds)

    async def _subscribe(self) -> None:
        handlers = {AutopilotEventType.ERROR_OCCURRED: self._on_error, AutopilotEventType.QUEUE_EMPTY: self._on_queue_empty, AutopilotEventType.SCHEDULE_TRIGGERED: self._on_schedule_triggered, AutopilotEventType.LIVE_MODE_STARTED: self._on_live_started, AutopilotEventType.LIVE_MODE_ENDED: self._on_live_ended}
        for event_type, handler in handlers.items():
            subscription = await self._event_bus.subscribe(event_type, handler, f"autopilot_manager:{event_type.value}")
            self._subscriptions.append((event_type, subscription))

    async def _unsubscribe(self) -> None:
        for event_type, subscription in self._subscriptions:
            await self._event_bus.unsubscribe(event_type, subscription)
        self._subscriptions.clear()

    async def _on_error(self, event: AutopilotEvent) -> None:
        # RecoveryManager emits an ERROR_OCCURRED record for auditability; that
        # event describes the chosen recovery and must not recursively recover.
        if "recovery_action" in event.payload:
            return
        state = await self._state_manager.snapshot()
        if not state.autopilot_enabled or state.manual_override:
            return
        now = datetime.now(timezone.utc)
        if self._last_recovery_at and now - self._last_recovery_at < timedelta(seconds=30):
            logger.warning("Autopilot recovery suppressed during cooldown", extra={"correlation_id": event.correlation_id})
            return
        self._last_recovery_at = now
        candidates = await self._media_provider()
        action = await self._recovery_manager.recover(state, candidates, str(event.payload.get("error", "Unknown autopilot fault")))
        await self._dispatch(action)

    async def _on_queue_empty(self, _: AutopilotEvent) -> None:
        state = await self._state_manager.snapshot()
        if not state.autopilot_enabled or state.manual_override:
            return
        action = self._queue_manager.refill_action(state, await self._media_provider())
        await self._dispatch(action)

    async def _on_schedule_triggered(self, event: AutopilotEvent) -> None:
        state = await self._state_manager.snapshot()
        if not state.autopilot_enabled or state.manual_override:
            return
        schedule_id = event.payload.get("schedule_id")
        await self._state_manager.update(lambda current: current.evolve(last_event=f"SCHEDULE_TRIGGERED:{schedule_id}"))
        event_type = str(event.payload.get("event_type", "playlist")).lower()
        mapping = {"playlist": ActionType.PLAY_PLAYLIST, "advertisement": ActionType.PLAY_ADS, "jingle": ActionType.PLAY_JINGLE, "announcement": ActionType.PLAY_JINGLE, "news": ActionType.LOAD_QUEUE}
        action = AutopilotAction(mapping.get(event_type, ActionType.LOAD_QUEUE), f"Execute due {event_type} schedule", dict(event.payload), priority=10, correlation_id=event.correlation_id)
        await self._dispatch(action)

    async def _on_live_started(self, _: AutopilotEvent) -> None:
        await self._state_manager.update(lambda state: state.evolve(live_mode=True))

    async def _on_live_ended(self, _: AutopilotEvent) -> None:
        await self._state_manager.update(lambda state: state.evolve(live_mode=False))

    async def _dispatch(self, action: AutopilotAction) -> None:
        if action.is_noop:
            return
        try:
            await self._action_executor(action)
            logger.info("Autopilot action handed to backend service executor", extra={"action": action.action_type.value, "correlation_id": action.correlation_id})
        except Exception as error:
            logger.exception("Backend service action executor failed", extra={"action": action.action_type.value, "correlation_id": action.correlation_id})
            await self._event_bus.publish(AutopilotEvent(AutopilotEventType.ERROR_OCCURRED, {"error": str(error), "action": action.to_dict(), "component": "backend_service_executor"}, source="autopilot_manager", correlation_id=action.correlation_id))
