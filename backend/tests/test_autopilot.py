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
async def test_news_schedule_prepares_before_then_broadcasts_once() -> None:
    """A news bulletin is prepared in advance and is broadcast only at airtime."""
    bus = EventBus()
    received: list[AutopilotEvent] = []

    async def record(event: AutopilotEvent) -> None:
        received.append(event)

    await bus.subscribe(AutopilotEventType.SCHEDULE_TRIGGERED, record)
    run_at = datetime.now(timezone.utc) + timedelta(minutes=10)
    news = ScheduleRef(
        id=8,
        event_type="news",
        run_at=run_at,
        payload={"preparation_minutes": 10, "duration_seconds": 60},
    )

    async def provider() -> tuple[ScheduleRef, ...]:
        return (news,)

    executor = ScheduleExecutor(provider, bus)
    assert await executor.poll(run_at - timedelta(minutes=10)) == ()
    assert [event.payload["phase"] for event in received] == ["prepare"]
    assert await executor.poll(run_at - timedelta(minutes=5)) == ()
    assert len(received) == 1
    assert await executor.poll(run_at) == (news,)
    assert [event.payload["phase"] for event in received] == ["prepare", "broadcast"]


@pytest.mark.asyncio
async def test_state_manager_restores_persisted_snapshot(tmp_path) -> None:
    """State snapshots survive a restart when persistence is configured."""
    path = tmp_path / "autopilot-state.json"
    manager = StateManager(persistence_path=path)
    await manager.replace(StationState(autopilot_enabled=True, current_mode="AUTOPILOT"))
    restored = await StateManager(persistence_path=path).restore()
    assert restored.autopilot_enabled is True
    assert restored.current_mode == "AUTOPILOT"


@pytest.mark.asyncio
async def test_scheduled_playlist_waits_for_active_track_before_playing() -> None:
    """Scheduled playlist completes current track first and then plays next."""
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from models.entities import Base, Playlist, Schedule, Song
    from playback.controller import playback_controller
    from repositories.radio import RadioRepository
    from services.radio import RadioService

    await playback_controller.clear_queue()
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        repo = RadioRepository(session)
        s_now = await repo.add_song(Song(title="Now Playing", artist="Artist 1", file_path="/tmp/now.mp3", duration_seconds=180))
        s_old_q = await repo.add_song(Song(title="Old Queued", artist="Artist 2", file_path="/tmp/old.mp3", duration_seconds=180))
        s_sched = await repo.add_song(Song(title="Scheduled Song", artist="Artist 3", file_path="/tmp/sched.mp3", duration_seconds=180))

        pl = await repo.add_playlist(Playlist(name="Evening Show"))
        await repo.add_to_playlist(pl, s_sched)
        sched = await repo.add_schedule(
            Schedule(name="Evening Show", event_type="playlist", playlist_id=pl.id, run_at=datetime.now(timezone.utc), enabled=True)
        )

        service = RadioService(session)
        await service.play(s_now.id, "tester")
        await service.enqueue_song(s_old_q.id, "tester")
        before = await service.state()
        rev_before = before.playback_revision

        # Trigger scheduled playlist while s_now is playing: must NOT interrupt s_now
        after_trigger = await service.run_scheduled_playlist(sched.id, pl.id, actor="scheduler")
        assert after_trigger.current_song is not None
        assert after_trigger.current_song.id == s_now.id
        assert [q.id for q in after_trigger.queue] == [s_sched.id, s_old_q.id]

        # Complete s_now -> s_sched plays next
        after_end = await service.track_ended(rev_before, "tester")
        assert after_end.current_song is not None
        assert after_end.current_song.id == s_sched.id
        assert [q.id for q in after_end.queue] == [s_old_q.id]

    await playback_controller.clear_queue()
    await playback_controller.stop()
    await engine.dispose()


@pytest.mark.asyncio
async def test_scheduled_news_waits_for_active_track_then_broadcasts_before_playlist() -> None:
    """Scheduled news does not cut into an active song; it airs after current track completes and before queued items."""
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from models.entities import Base, Playlist, Schedule, Song
    from playback.controller import playback_controller
    from repositories.radio import RadioRepository
    from services.radio import RadioService

    await playback_controller.clear_queue()
    await playback_controller.clear_news_broadcasting()
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        repo = RadioRepository(session)
        s_now = await repo.add_song(Song(title="Playing Track", artist="Artist 1", file_path="/tmp/playing.mp3", duration_seconds=0))
        s_sched = await repo.add_song(Song(title="After News Track", artist="Artist 2", file_path="/tmp/after.mp3", duration_seconds=180))

        pl = await repo.add_playlist(Playlist(name="Post-News Show"))
        await repo.add_to_playlist(pl, s_sched)
        sched_news = await repo.add_schedule(
            Schedule(
                name="Top News",
                event_type="news",
                run_at=datetime.now(timezone.utc),
                enabled=True,
                metadata_json={"duration_seconds": 60, "bullets": ["Headline 1"], "script": "Top news bulletin."},
            )
        )
        sched_pl = await repo.add_schedule(
            Schedule(name="Post-News Show", event_type="playlist", playlist_id=pl.id, run_at=datetime.now(timezone.utc), enabled=True)
        )

        service = RadioService(session)
        await service.play(s_now.id, "tester")
        rev_before = (await service.state()).playback_revision

        # Schedule news + playlist trigger while s_now is playing
        aired_now = await service.trigger_scheduled_news(sched_news.id, actor="scheduler_news")
        assert aired_now is False
        assert "broadcast_at" not in ((await repo.get_schedule(sched_news.id)).metadata_json or {})

        await service.run_scheduled_playlist(sched_pl.id, pl.id, actor="scheduler")
        mid_state = await service.state()
        assert mid_state.current_song is not None and mid_state.current_song.id == s_now.id
        assert mid_state.status == "playing"

        # Current track completes -> news must air first, holding s_sched in queue until news finishes
        ended_state = await service.track_ended(rev_before, "tester")
        assert ended_state.status == "stopped"
        assert ended_state.current_song is None
        assert [q.id for q in ended_state.queue] == [s_sched.id]
        updated_news = await repo.get_schedule(sched_news.id)
        assert updated_news is not None
        assert updated_news.enabled is False
        assert "broadcast_at" in (updated_news.metadata_json or {})
        assert await playback_controller.is_news_broadcasting() is True

        # As soon as NOVA voice finishes reading (~20s), complete_news_broadcast starts s_sched immediately without waiting 60s
        resumed_state = await service.complete_news_broadcast(sched_news.id, actor="nova_voice")
        assert resumed_state.status == "playing"
        assert resumed_state.current_song is not None and resumed_state.current_song.id == s_sched.id
        assert resumed_state.queue == []
        assert "completed_at" in ((await repo.get_schedule(sched_news.id)).metadata_json or {})
        assert await playback_controller.is_news_broadcasting() is False

    await playback_controller.clear_news_broadcasting()
    await playback_controller.clear_queue()
    await playback_controller.stop()
    await engine.dispose()
