"""Application adapter that connects decision-only autopilot to backend services."""

from __future__ import annotations

import asyncio
from collections.abc import Iterable
from datetime import datetime, timezone
import logging
from pathlib import Path

from autopilot.autopilot_manager import AutopilotManager
from autopilot.autopilot_state import ActionType, AutopilotAction, MediaRef, ScheduleRef, StationState
from autopilot.decision_engine import DecisionEngine
from autopilot.event_bus import EventBus
from autopilot.monitoring_service import MonitoringService, PlaybackObservation
from autopilot.queue_manager import QueueManager
from autopilot.recovery_manager import RecoveryManager
from autopilot.schedule_executor import ScheduleExecutor
from autopilot.state_manager import StateManager
from core.config import settings
from database.session import SessionLocal
from sqlalchemy.ext.asyncio import AsyncSession
from repositories.radio import RadioRepository
from services.radio import RadioService
from tools.news_tool import NewsTool

logger = logging.getLogger(__name__)


class AutopilotRuntime:
    """Compose autopilot policy components with the established service boundary."""

    def __init__(self) -> None:
        event_bus = EventBus()
        queue_manager = QueueManager()
        self._manager = AutopilotManager(
            state_manager=StateManager(persistence_path=settings.media_path / ".autopilot-state.json"),
            decision_engine=DecisionEngine(),
            event_bus=event_bus,
            queue_manager=queue_manager,
            schedule_executor=ScheduleExecutor(self._schedule_provider, event_bus),
            monitoring_service=MonitoringService(self._playback_probe, event_bus),
            recovery_manager=RecoveryManager(queue_manager, event_bus),
            state_provider=self._station_state_provider,
            media_provider=self._media_provider,
            action_executor=self._execute_action,
        )

    @property
    def running(self) -> bool:
        """Return whether the decision loop is active."""
        return self._manager.running

    async def start(self) -> None:
        """Start the decision loop after backend mode ownership changes."""
        await self._manager.start()

    async def stop(self, manual_override: bool = True) -> None:
        """Stop the decision loop without changing playback directly."""
        await self._manager.stop(manual_override=manual_override)

    async def shutdown(self) -> None:
        """Persist state and release the background task during application shutdown."""
        if self.running:
            await self.stop(manual_override=False)

    @staticmethod
    def _media(song: object) -> MediaRef:
        """Map a persisted or API song object to policy-safe media metadata."""
        song_id = int(getattr(song, "id"))
        file_path = Path(str(getattr(song, "file_path")))
        return MediaRef(
            id=song_id,
            title=str(getattr(song, "title")),
            artist=str(getattr(song, "artist", "Unknown Artist")),
            duration_seconds=float(getattr(song, "duration_seconds", 0.0)),
            available=file_path.is_file(),
        )

    @staticmethod
    def _schedule(entry: object) -> ScheduleRef:
        """Map a persisted schedule object to the immutable policy contract."""
        run_at = getattr(entry, "run_at")
        if run_at.tzinfo is None:
            run_at = run_at.replace(tzinfo=timezone.utc)
        return ScheduleRef(
            id=int(getattr(entry, "id")),
            event_type=str(getattr(entry, "event_type")),
            run_at=run_at,
            playlist_id=getattr(entry, "playlist_id"),
            payload=dict(getattr(entry, "metadata_json", {}) or {}),
            enabled=bool(getattr(entry, "enabled")),
        )

    async def _station_state_provider(self) -> StationState:
        """Read station state through services and repositories, never an audio engine."""
        async with SessionLocal() as session:
            service = RadioService(session)
            playback = await service.state()
            schedules = await RadioRepository(session).list_schedules()
            return StationState(
                current_song=self._media(playback.current_song) if playback.current_song else None,
                queue=tuple(self._media(song) for song in playback.queue),
                playback_position=playback.current_position_seconds,
                current_mode=playback.mode,
                autopilot_enabled=playback.mode.upper() == "AUTOPILOT",
                schedule=tuple(self._schedule(entry) for entry in schedules),
            )

    async def _schedule_provider(self) -> Iterable[ScheduleRef]:
        """Read schedules for policy evaluation."""
        async with SessionLocal() as session:
            schedules = await RadioRepository(session).list_schedules()
            return tuple(self._schedule(entry) for entry in schedules)

    async def _media_provider(self) -> Iterable[MediaRef]:
        """Read eligible library media for queue and recovery decisions."""
        async with SessionLocal() as session:
            songs = await RadioRepository(session).list_songs()
            return tuple(self._media(song) for song in songs)

    async def _playback_probe(self) -> PlaybackObservation:
        """Observe existing playback state through RadioService only."""
        async with SessionLocal() as session:
            playback = await RadioService(session).state()
            return PlaybackObservation(
                status=playback.status,
                current_song=self._media(playback.current_song) if playback.current_song else None,
                queue_depth=len(playback.queue),
                playback_position=playback.current_position_seconds,
                observed_at=datetime.now(timezone.utc),
            )

    async def _execute_action(self, action: AutopilotAction) -> None:
        """Delegate a structured policy result to established backend service methods."""
        async with SessionLocal() as session:
            service = RadioService(session)
            if action.action_type is ActionType.PLAY_PLAYLIST:
                playlist_id = action.payload.get("playlist_id")
                if not isinstance(playlist_id, int):
                    raise ValueError("PLAY_PLAYLIST requires an integer playlist_id")
                await service.run_playlist(playlist_id, actor="autopilot", interrupt_current=isinstance(action.payload.get("schedule_id"), int))
                return
            if action.action_type in {ActionType.LOAD_QUEUE, ActionType.PLAY_ADS, ActionType.PLAY_JINGLE}:
                song_ids = self._song_ids(action)
                if not song_ids:
                    await service.log("autopilot", "Autopilot action has no executable media IDs", "autopilot", action.to_dict())
                    return
                state = await service.state()
                existing_ids = {song.id for song in state.queue}
                if state.current_song:
                    existing_ids.add(state.current_song.id)
                accepted_ids = tuple(song_id for song_id in song_ids if song_id not in existing_ids)
                for song_id in accepted_ids:
                    await service.enqueue_song(song_id, actor="autopilot")
                state = await service.state()
                if state.status == "stopped":
                    await service.play(None, actor="autopilot")
                await service.log("autopilot", "Autopilot queue refill executed", "autopilot", {"requested_song_ids": list(song_ids), "accepted_song_ids": list(accepted_ids), "queue_depth": len(state.queue)})
                return
            if action.action_type is ActionType.RECOVER_PLAYBACK:
                song_ids = self._song_ids(action, "replacement_song_ids")
                state = await service.state()
                existing_ids = {song.id for song in state.queue}
                if state.current_song:
                    existing_ids.add(state.current_song.id)
                accepted_ids = tuple(song_id for song_id in song_ids if song_id not in existing_ids)
                for song_id in accepted_ids:
                    await service.enqueue_song(song_id, actor="autopilot")
                state = await service.state()
                if state.status in {"stopped", "paused"} and (accepted_ids or state.queue):
                    await service.play(None, actor="autopilot")
                await service.log("autopilot", "Autopilot recovery action executed", "autopilot", action.to_dict())
                return
            if action.action_type is ActionType.SKIP_TRACK:
                await service.command("skip", actor="autopilot")
                return
            if action.action_type is ActionType.PREPARE_NEWS:
                await self._prepare_news(session, service, action)
                return
            if action.action_type is ActionType.PLAY_NEWS:
                await self._broadcast_news(session, service, action)
                return
            await service.log("autopilot", "Autopilot decision recorded", "autopilot", action.to_dict())
            logger.info("Autopilot action has no matching station execution capability", extra={"action": action.action_type.value})

    @staticmethod
    def _song_ids(action: AutopilotAction, key: str = "song_ids") -> tuple[int, ...]:
        """Extract validated media identifiers from a structured action payload."""
        raw_ids = action.payload.get(key, action.payload.get("song_ids", []))
        if not isinstance(raw_ids, (list, tuple)):
            return ()
        return tuple(item for item in raw_ids if isinstance(item, int) and item > 0)

    async def _prepare_news(self, session: AsyncSession, service: RadioService, action: AutopilotAction) -> None:
        schedule_id = action.payload.get("schedule_id")
        if not isinstance(schedule_id, int):
            raise ValueError("PREPARE_NEWS requires schedule_id")
        repository = RadioRepository(session)
        schedule = await repository.get_schedule(schedule_id)
        if not schedule:
            raise LookupError("News schedule not found")
        duration = int(action.payload.get("duration_seconds", 60))
        mix = action.payload.get("mix", ["headlines", "weather", "station"])
        bulletin = await NewsTool.automatic_bulletin(duration, mix if isinstance(mix, list) else None)
        schedule.metadata_json = {**(schedule.metadata_json or {}), **bulletin}
        await session.commit()
        await service.log("news", "Autopilot prepared news bulletin", "autopilot", {"schedule_id": schedule_id, "bullet_count": len(bulletin["bullets"])})

    async def _broadcast_news(self, session: AsyncSession, service: RadioService, action: AutopilotAction) -> None:
        schedule_id = action.payload.get("schedule_id")
        schedule = await RadioRepository(session).get_schedule(schedule_id) if isinstance(schedule_id, int) else None
        bulletin = (schedule.metadata_json or {}) if schedule else {}
        if not bulletin.get("bullets"):
            bulletin = await NewsTool.automatic_bulletin(int(action.payload.get("duration_seconds", 60)))
        if schedule:
            schedule.metadata_json = {
                **(schedule.metadata_json or {}),
                **bulletin,
                "broadcast_at": datetime.now(timezone.utc).isoformat(),
            }
            await session.commit()
        playback = await service.state()
        duration = max(30, min(120, int(bulletin.get("duration_seconds", action.payload.get("duration_seconds", 60)))))
        if playback.status == "playing":
            await service.command("pause", actor="autopilot_news")
            asyncio.create_task(self._resume_after_news(duration), name=f"radiopilot-news-resume-{schedule_id}")
        await service.log("news", "Autopilot news bulletin triggered", "autopilot", {"schedule_id": schedule_id, **bulletin})

    async def _resume_after_news(self, duration_seconds: int) -> None:
        """Resume a paused Autopilot music bed after its bounded spoken bulletin."""
        await asyncio.sleep(duration_seconds)
        async with SessionLocal() as session:
            service = RadioService(session)
            state = await service.state()
            if state.mode == "AUTOPILOT" and state.status == "paused":
                await service.command("resume", actor="autopilot_news")


autopilot_runtime = AutopilotRuntime()
