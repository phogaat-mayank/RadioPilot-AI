"""Station application service coordinating repositories and playback."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import logging
from sqlalchemy.ext.asyncio import AsyncSession

from models.entities import AuditLog, PlaybackHistory, Playlist, Schedule, Song, StationMode
from playback.controller import playback_controller
from repositories.radio import RadioRepository
from schemas.radio import PlaybackState, PlaylistCreate, ScheduleCreate, SongCreate
from websocket.manager import manager

logger = logging.getLogger(__name__)
_NEWS_WATCHERS: dict[int, asyncio.Task[None]] = {}


class RadioService:
    """Implement station behaviors independently of HTTP transport."""

    def __init__(self, session: AsyncSession) -> None:
        """Create a service scoped to a database unit of work."""
        self.session = session
        self.repository = RadioRepository(session)

    async def state(self) -> PlaybackState:
        """Combine controller state and persisted station mode."""
        controller_state = await playback_controller.state()
        system = await self.repository.get_state()
        return PlaybackState(mode=system.mode.value, **controller_state)

    async def emit_state(self) -> PlaybackState:
        """Broadcast the latest state after a successful station change."""
        state = await self.state()
        await manager.broadcast(state.model_dump(mode="json"))
        return state

    async def log(self, category: str, message: str, actor: str = "system", details: dict | None = None) -> None:
        """Write an audit record without making station actions fail on logging."""
        self.session.add(AuditLog(category=category, message=message, actor=actor, details=details or {}))
        await self.session.commit()
        logger.info(message, extra={"category": category, "actor": actor})

    async def add_song(self, payload: SongCreate, file_path: str) -> Song:
        """Register an uploaded sound asset."""
        return await self.repository.add_song(Song(**payload.model_dump(), file_path=file_path))

    async def create_playlist(self, payload: PlaylistCreate) -> Playlist:
        """Create a named playlist."""
        return await self.repository.add_playlist(Playlist(**payload.model_dump()))

    async def enqueue_song(self, song_id: int, actor: str) -> PlaybackState:
        """Place a library asset in the broadcast queue."""
        song = await self._require_song(song_id)
        await playback_controller.queue(song)
        await self.log("playback", f"Queued {song.title}", actor, {"song_id": song.id})
        return await self.emit_state()

    async def clear_queue(self, actor: str) -> PlaybackState:
        """Clear all pending assets from the broadcast queue."""
        count = await playback_controller.clear_queue()
        await self.log("playback", f"Cleared live queue ({count} items)", actor, {"cleared_count": count})
        return await self.emit_state()

    async def play(self, song_id: int | None, actor: str) -> PlaybackState:
        """Execute playback via the controller, never via an AI workflow."""
        song = await self._require_song(song_id) if song_id is not None else None
        await playback_controller.play(song)
        current = (await playback_controller.state())["current_song"]
        self.session.add(PlaybackHistory(song_id=current.id if current else None, action="play", performed_by=actor))
        await self.session.commit()
        await self.log("playback", "Playback started", actor)
        return await self.emit_state()

    async def command(self, command: str, actor: str) -> PlaybackState:
        """Execute a safe named playback command."""
        if command == "skip":
            pending_news_id, _ = await playback_controller.advance_or_trigger_pending_news(None)
            self.session.add(PlaybackHistory(action=command, performed_by=actor))
            await self.session.commit()
            if pending_news_id is not None:
                await self.broadcast_pending_news(pending_news_id, actor="scheduler_news")
            else:
                await self.log("playback", "Playback skip", actor)
            return await self.emit_state()

        actions = {"pause": playback_controller.pause, "resume": playback_controller.resume, "stop": playback_controller.stop, "previous": playback_controller.previous}
        if command not in actions:
            raise ValueError("Unsupported playback command")
        await actions[command]()
        self.session.add(PlaybackHistory(action=command, performed_by=actor))
        await self.session.commit()
        await self.log("playback", f"Playback {command}", actor)
        return await self.emit_state()

    async def track_ended(self, playback_revision: int, actor: str) -> PlaybackState:
        """Advance after track ends: broadcast any pending news first, otherwise start next queued track."""
        pending_news_id, handled = await playback_controller.advance_or_trigger_pending_news(playback_revision)
        if handled:
            self.session.add(PlaybackHistory(action="ended", performed_by=actor))
            await self.session.commit()
            if pending_news_id is not None:
                await self.broadcast_pending_news(pending_news_id, actor="scheduler_news")
            else:
                await self.log("playback", "Playback advanced after track ended", actor, {"playback_revision": playback_revision})
        return await self.emit_state()

    async def set_volume(self, volume: int, actor: str) -> PlaybackState:
        """Change playback and persistent station volume."""
        await playback_controller.set_volume(volume)
        state = await self.repository.get_state()
        state.volume = volume
        await self.session.commit()
        await self.log("playback", f"Volume changed to {volume}", actor)
        return await self.emit_state()

    async def set_mode(self, mode: str, actor: str) -> PlaybackState:
        """Switch control ownership without interrupting playback."""
        state = await self.repository.get_state()
        state.mode = StationMode(mode)
        await self.session.commit()
        await self.log("mode", f"Mode changed to {mode}", actor)
        return await self.emit_state()

    async def schedule(self, payload: ScheduleCreate) -> Schedule:
        """Persist a schedule; scheduler registration is handled by caller."""
        data = payload.model_dump()
        station_tz = ZoneInfo("Asia/Kolkata")
        run_at: datetime = data["run_at"]
        if run_at.tzinfo is None:
            data["run_at"] = run_at.replace(tzinfo=station_tz).astimezone(timezone.utc)
        else:
            data["run_at"] = run_at.astimezone(timezone.utc)
        return await self.repository.add_schedule(Schedule(**data))

    async def run_playlist(self, playlist_id: int, actor: str = "scheduler", interrupt_current: bool = False) -> PlaybackState:
        """Queue a playlist or play it immediately while preserving the prior queue."""
        playlist = await self.repository.get_playlist(playlist_id)
        if not playlist or not playlist.items:
            raise ValueError("Playlist is unavailable or empty")
        songs = [item.song for item in playlist.items]
        if interrupt_current:
            await playback_controller.interrupt_with_playlist(songs)
        else:
            await playback_controller.queue_many(songs)
        state = await playback_controller.state()
        if not interrupt_current and state["status"] == "stopped":
            await playback_controller.play()
        action = "Interrupted with" if interrupt_current else "Started"
        await self.log("scheduler", f"{action} playlist {playlist.name}", actor, {"playlist_id": playlist.id, "interrupt_current": interrupt_current})
        return await self.emit_state()

    async def run_scheduled_playlist(self, schedule_id: int | None, playlist_id: int, actor: str = "scheduler") -> PlaybackState:
        """Play a scheduled playlist after any currently playing track finishes."""
        schedule = await self.repository.get_schedule(schedule_id) if schedule_id is not None else None
        if schedule is not None and not schedule.enabled:
            return await self.state()

        playlist = await self.repository.get_playlist(playlist_id)
        if not playlist or not playlist.items:
            if schedule is not None:
                schedule.enabled = False
                await self.session.commit()
            raise ValueError("Playlist is unavailable or empty")

        songs = [item.song for item in playlist.items]
        started_now = await playback_controller.enqueue_scheduled_playlist(songs)
        if schedule is not None:
            schedule.enabled = False
            await self.session.commit()

        msg = (
            f"Started scheduled playlist {playlist.name}"
            if started_now
            else f"Queued scheduled playlist {playlist.name} after current track"
        )
        await self.log("scheduler", msg, actor, {"schedule_id": schedule_id, "playlist_id": playlist.id, "started_immediately": started_now})
        return await self.emit_state()

    async def is_news_broadcasting(self) -> bool:
        """Return whether a scheduled spoken news bulletin is currently airing."""
        return await playback_controller.is_news_broadcasting()

    async def trigger_scheduled_news(
        self,
        schedule_id: int,
        metadata: dict | None = None,
        actor: str = "scheduler_news",
    ) -> bool:
        """Prepare a scheduled news bulletin; defer airing until active track completes if playing.

        Returns True if aired immediately, False if deferred behind an active track (or already aired).
        """
        from tools.news_tool import NewsTool

        schedule = await self.repository.get_schedule(schedule_id)
        if schedule is not None and (schedule.metadata_json or {}).get("broadcast_at"):
            return False

        merged_meta = {**((schedule.metadata_json or {}) if schedule else {}), **(metadata or {})}
        duration = max(30, min(120, int(merged_meta.get("duration_seconds", 60))))
        if not merged_meta.get("bullets"):
            mix = merged_meta.get("mix", ["headlines", "weather", "station"])
            bulletin = await NewsTool.automatic_bulletin(duration, mix if isinstance(mix, list) else None)
            merged_meta.update(bulletin)

        if schedule is not None:
            schedule.metadata_json = merged_meta
            await self.session.commit()

        deferred, expected_rev, total_dur, remaining = await playback_controller.queue_pending_news_if_playing(schedule_id)
        if deferred:
            state = await self.state()
            track_name = state.current_song.title if state.current_song else "active track"
            await self.log(
                "news",
                f"Scheduled news queued until '{track_name}' finishes",
                actor,
                {"schedule_id": schedule_id, "playback_revision": expected_rev},
            )
            if total_dur > 0:
                existing_watcher = _NEWS_WATCHERS.pop(schedule_id, None)
                if existing_watcher and not existing_watcher.done():
                    existing_watcher.cancel()
                _NEWS_WATCHERS[schedule_id] = asyncio.create_task(
                    self._watch_track_end_for_news(schedule_id, expected_rev, remaining + 2.5)
                )
            await self.emit_state()
            return False

        await self._activate_news_broadcast(schedule, merged_meta, duration, actor)
        await self.emit_state()
        return True

    async def broadcast_pending_news(self, schedule_id: int, actor: str = "scheduler_news") -> None:
        """Air a previously deferred news bulletin immediately upon current track completion."""
        watcher = _NEWS_WATCHERS.pop(schedule_id, None)
        if watcher and not watcher.done():
            watcher.cancel()

        schedule = await self.repository.get_schedule(schedule_id)
        if schedule is not None and (schedule.metadata_json or {}).get("broadcast_at"):
            return

        meta = dict(schedule.metadata_json or {}) if schedule else {}
        duration = max(30, min(120, int(meta.get("duration_seconds", 60))))
        if not meta.get("bullets"):
            from tools.news_tool import NewsTool
            mix = meta.get("mix", ["headlines", "weather", "station"])
            meta.update(await NewsTool.automatic_bulletin(duration, mix if isinstance(mix, list) else None))

        await self._activate_news_broadcast(schedule, meta, duration, actor)

    async def _activate_news_broadcast(
        self,
        schedule: Schedule | None,
        metadata: dict,
        duration: int,
        actor: str,
    ) -> None:
        """Mark news active on air and schedule bounded fallback resumption after bulletin duration."""
        from scheduler.service import schedule_news_resume

        if schedule is not None:
            meta = dict(metadata)
            meta.pop("completed_at", None)
            schedule.metadata_json = {
                **meta,
                "duration_seconds": duration,
                "broadcast_at": datetime.now(timezone.utc).isoformat(),
            }
            schedule.enabled = False
            await self.session.commit()

        await playback_controller.set_news_broadcasting(duration)
        schedule_news_resume(duration)
        await self.log(
            "news",
            f"Scheduled news bulletin broadcasting ({duration}s max window)",
            actor,
            {"schedule_id": schedule.id if schedule else None, "duration_seconds": duration},
        )

    async def complete_news_broadcast(self, schedule_id: int | None = None, actor: str = "nova_voice") -> PlaybackState:
        """End the active news window immediately once NOVA finishes reading, then play next track."""
        from scheduler.service import cancel_news_resume

        cancel_news_resume()
        await playback_controller.clear_news_broadcasting()

        if schedule_id is not None:
            schedule = await self.repository.get_schedule(schedule_id)
            if schedule is not None:
                meta = dict(schedule.metadata_json or {})
                if not meta.get("completed_at"):
                    meta["completed_at"] = datetime.now(timezone.utc).isoformat()
                    schedule.metadata_json = meta
                    schedule.enabled = False
                    await self.session.commit()

        state = await self.state()
        if state.status == "paused":
            await playback_controller.resume()
            self.session.add(PlaybackHistory(action="resume", performed_by=actor))
            await self.session.commit()
            await self.log("news", "News bulletin finished; playback resumed", actor, {"schedule_id": schedule_id})
        elif state.status != "playing" and state.queue:
            await playback_controller.play(None)
            current = (await playback_controller.state())["current_song"]
            self.session.add(PlaybackHistory(song_id=current.id if current else None, action="play", performed_by=actor))
            await self.session.commit()
            await self.log("news", "News bulletin finished; next track started", actor, {"schedule_id": schedule_id})
        else:
            await self.log("news", "News bulletin finished", actor, {"schedule_id": schedule_id})

        return await self.emit_state()

    @staticmethod
    async def _watch_track_end_for_news(schedule_id: int, expected_revision: int, wait_seconds: float) -> None:
        """Headless fallback timer: trigger deferred news if active track reaches duration without browser event."""
        try:
            await asyncio.sleep(max(1.0, wait_seconds))
            _NEWS_WATCHERS.pop(schedule_id, None)
            pending_news_id, handled = await playback_controller.advance_or_trigger_pending_news(expected_revision)
            if handled and pending_news_id is not None:
                from database.session import SessionLocal
                async with SessionLocal() as session:
                    service = RadioService(session)
                    await service.broadcast_pending_news(pending_news_id, actor="scheduler_news_fallback")
                    await service.emit_state()
        except asyncio.CancelledError:
            pass

    async def _require_song(self, song_id: int) -> Song:
        """Fetch a song or raise a transport-neutral not-found error."""
        song = await self.repository.get_song(song_id)
        if song is None:
            raise LookupError("Song not found")
        return song
