"""Unit tests for the decision-only autopilot subsystem."""

from datetime import datetime, timedelta, timezone

import pytest

from autopilot.autopilot_events import AutopilotEvent, AutopilotEventType
from autopilot.autopilot_state import ActionType, MediaRef, ScheduleRef, StationState
from autopilot.decision_engine import DecisionEngine
from autopilot.event_bus import EventBus
from autopilot.monitoring_service import MonitoringService, PlaybackObservation
from autopilot.queue_manager import QueueManager
from autopilot.schedule_executor import ScheduleExecutor
from autopilot.state_manager import StateManager


def test_decision_engine_respects_manual_override() -> None:
    """Manual mode always blocks decision actions."""
    action = DecisionEngine().decide(StationState(autopilot_enabled=True, manual_override=True, current_mode="MANUAL"))
    assert action.action_type is ActionType.NO_ACTION


def test_decision_engine_does_not_repeat_schedule_execution() -> None:
    """Due schedules are executed once by ScheduleExecutor, not every policy poll."""
    due = ScheduleRef(id=7, event_type="playlist", run_at=datetime.now(timezone.utc) - timedelta(seconds=1), playlist_id=22)
    action = DecisionEngine().decide(StationState(autopilot_enabled=True, current_mode="AUTOPILOT", queue=(MediaRef(3, "Queued"),), schedule=(due,)))
    assert action.action_type is ActionType.NO_ACTION


def test_queue_manager_avoids_current_and_queued_media() -> None:
    """Queue refill never repeats current or already queued songs."""
    current = MediaRef(1, "Current")
    queued = MediaRef(2, "Queued")
    action = QueueManager(minimum_depth=3, maximum_depth=4).refill_action(StationState(current_song=current, queue=(queued,)), [current, queued, MediaRef(3, "Eligible"), MediaRef(4, "Eligible two")])
    assert action.action_type is ActionType.LOAD_QUEUE
    assert set(action.payload["song_ids"]) == {3, 4}


@pytest.mark.asyncio
async def test_monitor_resets_progress_for_a_new_track() -> None:
    """A new track starting at zero must not be marked stalled due to the old track position."""
    bus = EventBus()
    observations = iter((
        PlaybackObservation("playing", MediaRef(1, "First"), 2, 180, datetime.now(timezone.utc)),
        PlaybackObservation("playing", MediaRef(2, "Second"), 2, 0, datetime.now(timezone.utc) + timedelta(seconds=1)),
    ))

    async def probe() -> PlaybackObservation:
        return next(observations)

    monitor = MonitoringService(probe, bus, idle_threshold_seconds=20)
    await monitor.poll()
    _, health = await monitor.poll()
    assert health.playback_healthy is True


@pytest.mark.asyncio
async def test_event_bus_and_schedule_executor_publish_once() -> None:
    """Due schedules emit one event, then remain de-duplicated on later polls."""
    bus = EventBus()
    received: list[AutopilotEvent] = []

    async def record(event: AutopilotEvent) -> None:
        received.append(event)

    await bus.subscribe(AutopilotEventType.SCHEDULE_TRIGGERED, record)
    due = ScheduleRef(id=1, event_type="playlist", run_at=datetime.now(timezone.utc) - timedelta(seconds=1), playlist_id=2)

    async def provider() -> tuple[ScheduleRef, ...]:
        return (due,)

    executor = ScheduleExecutor(provider, bus)
    assert await executor.poll() == (due,)
    assert await executor.poll() == ()
    assert len(received) == 1


@pytest.mark.asyncio
async def test_state_manager_restores_persisted_snapshot(tmp_path) -> None:
    """State snapshots survive a restart when persistence is configured."""
    path = tmp_path / "autopilot-state.json"
    manager = StateManager(persistence_path=path)
    await manager.replace(StationState(autopilot_enabled=True, current_mode="AUTOPILOT"))
    restored = await StateManager(persistence_path=path).restore()
    assert restored.autopilot_enabled is True
    assert restored.current_mode == "AUTOPILOT"
