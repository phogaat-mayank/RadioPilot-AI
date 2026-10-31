"""Station application service coordinating repositories and playback."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import logging
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.entities import AIDJSettings, AuditLog, PlaybackHistory, Playlist, Schedule, Song, StationMode
from playback.controller import playback_controller
from repositories.radio import RadioRepository
from schemas.radio import AnnouncementOut, PlaybackState, PlaylistCreate, ScheduleCreate, SongCreate
from services.dj_voice_service import dj_voice_service
from websocket.manager import manager

logger = logging.getLogger(__name__)


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
        asyncio.create_task(self._pregenerate_next_dj_announcement())
        return await self.emit_state()

    _bg_tasks: set = set()

    def _schedule_pregen(self) -> None:
        """Safely schedule background announcement preparation."""
        try:
            loop = asyncio.get_running_loop()
            if loop.is_running():
                task = loop.create_task(self._pregenerate_next_dj_announcement())
                self._bg_tasks.add(task)
                task.add_done_callback(self._bg_tasks.discard)
        except RuntimeError:
            pass

    async def command(self, command: str, actor: str) -> PlaybackState:
        """Execute a safe named playback command."""
        actions = {"pause": playback_controller.pause, "resume": playback_controller.resume, "stop": playback_controller.stop, "skip": playback_controller.skip, "previous": playback_controller.previous}
        if command not in actions:
            raise ValueError("Unsupported playback command")
        await actions[command]()
        self.session.add(PlaybackHistory(action=command, performed_by=actor))
        await self.session.commit()
        await self.log("playback", f"Playback {command}", actor)
        if command in {"skip", "resume", "play"}:
            self._schedule_pregen()
        return await self.emit_state()

    async def track_ended(self, playback_revision: int, actor: str) -> PlaybackState:
        """Advance from an HTML audio ended event with safe AI DJ announcement sequencing."""
        # 1. Check if AI DJ announcement should play before advancing to the next song
        stmt = select(AIDJSettings).where(AIDJSettings.id == 1)
        res = await self.session.execute(stmt)
        dj_settings = res.scalar_one_or_none()

        ann = await dj_voice_service.get_and_consume_announcement(dj_settings)
        if ann is not None:
            await playback_controller.set_active_announcement(ann)
            self.session.add(PlaybackHistory(action="dj_announcement", performed_by=actor))
            await self.session.commit()
            await self.log("voice", f"AI DJ announcement on air: '{ann.text[:40]}'", actor, {"announcement_id": ann.id})
            return await self.emit_state()

        # 2. If no announcement or not due, advance directly to next track
        advanced = await playback_controller.skip_if_revision(playback_revision)
        if advanced:
            self.session.add(PlaybackHistory(action="ended", performed_by=actor))
            await self.session.commit()
            await self.log("playback", "Playback advanced after track ended", actor, {"playback_revision": playback_revision})
            self._schedule_pregen()
        return await self.emit_state()

    async def announcement_ended(self, playback_revision: int, actor: str) -> PlaybackState:
        """When an announcement finishes, clear it and advance to the next song."""
        await playback_controller.clear_active_announcement()
        await playback_controller.skip()
        self.session.add(PlaybackHistory(action="announcement_finished", performed_by=actor))
        await self.session.commit()
        await self.log("voice", "AI DJ announcement finished; started next song", actor)
        self._schedule_pregen()
        return await self.emit_state()

    async def trigger_announcement_now(self, announcement: AnnouncementOut, actor: str) -> PlaybackState:
        """Immediately air an announcement."""
        await playback_controller.set_active_announcement(announcement)
        await self.log("voice", f"Immediate announcement triggered: '{announcement.text[:40]}'", actor)
        return await self.emit_state()

    async def _pregenerate_next_dj_announcement(self) -> None:
        """Background task to synthesize the next announcement while current song plays."""
        try:
            await asyncio.sleep(1.0)
            st = await playback_controller.state()
            current_song = st.get("current_song")
            queue = st.get("queue") or []
            if not queue:
                return
            next_song = queue[0]

            from database.session import SessionLocal
            async with SessionLocal() as session:
                stmt = select(AIDJSettings).where(AIDJSettings.id == 1)
                res = await session.execute(stmt)
                dj_settings = res.scalar_one_or_none()
                if not dj_settings or not dj_settings.enabled:
                    return

                await dj_voice_service.prepare_next_announcement(
                    next_song_title=next_song.title,
                    next_song_artist=next_song.artist,
                    settings=dj_settings,
                    previous_song_title=current_song.title if current_song else None,
                    previous_song_artist=current_song.artist if current_song else None,
                )
        except asyncio.CancelledError:
            return
        except Exception as exc:
            logger.debug("Advance announcement preparation skipped: %s", exc)

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

    async def _require_song(self, song_id: int) -> Song:
        """Fetch a song or raise a transport-neutral not-found error."""
        song = await self.repository.get_song(song_id)
        if song is None:
            raise LookupError("Song not found")
        return song
