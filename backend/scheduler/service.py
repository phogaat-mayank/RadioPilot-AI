"""APScheduler coordinator for scheduled broadcast events."""

import asyncio
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import logging
from typing import Any
from apscheduler.schedulers.asyncio import AsyncIOScheduler

logger = logging.getLogger(__name__)


class StationScheduler:
    """Own APScheduler lifecycle and dispatch validated station work."""

    def __init__(self) -> None:
        """Create the scheduler in paused state."""
        self._scheduler = AsyncIOScheduler(timezone="UTC")

    def start(self) -> None:
        """Start job processing once the application has initialized."""
        if not self._scheduler.running:
            self._scheduler.start()

    def shutdown(self) -> None:
        """Stop scheduler without blocking graceful application shutdown."""
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)

    def register_schedule(
        self,
        schedule_id: int,
        event_type: str,
        playlist_id: int | None,
        run_at: datetime,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Register a scheduled event (playlist or news) in APScheduler."""
        station_tz = ZoneInfo("Asia/Kolkata")
        timestamp = run_at.astimezone(timezone.utc) if run_at.tzinfo else run_at.replace(tzinfo=station_tz).astimezone(timezone.utc)
        clean_type = str(event_type).lower().strip()
        job_id = f"schedule-{schedule_id}"

        if clean_type == "playlist" and playlist_id:
            self._scheduler.add_job(
                _run_playlist,
                "date",
                run_date=timestamp,
                args=[schedule_id, playlist_id],
                id=job_id,
                replace_existing=True,
                misfire_grace_time=600,
            )
            logger.info("Registered scheduled playlist job", extra={"schedule_id": schedule_id, "playlist_id": playlist_id, "run_at": timestamp.isoformat()})
        elif clean_type == "news":
            self._scheduler.add_job(
                _run_news,
                "date",
                run_date=timestamp,
                args=[schedule_id, metadata or {}],
                id=job_id,
                replace_existing=True,
                misfire_grace_time=600,
            )
            logger.info("Registered scheduled news bulletin job", extra={"schedule_id": schedule_id, "run_at": timestamp.isoformat()})

    def register_playlist(self, schedule_id: int, playlist_id: int, run_at: datetime) -> None:
        """Compatibility wrapper for legacy callers."""
        self.register_schedule(schedule_id, "playlist", playlist_id, run_at)

    def unregister(self, schedule_id: int) -> None:
        """Remove a job from APScheduler when deleted or cancelled."""
        job_id = f"schedule-{schedule_id}"
        try:
            if self._scheduler.get_job(job_id):
                self._scheduler.remove_job(job_id)
                logger.info("Unregistered schedule job", extra={"schedule_id": schedule_id})
        except Exception as ex:
            logger.warning("Could not unregister schedule %s: %s", schedule_id, ex)

    async def sync_database_schedules(self) -> int:
        """Sync and register all enabled upcoming schedules from the database."""
        from database.session import SessionLocal
        from repositories.radio import RadioRepository
        now = datetime.now(timezone.utc)
        count = 0
        async with SessionLocal() as session:
            repo = RadioRepository(session)
            schedules = await repo.list_schedules(upcoming_only=True)
            for s in schedules:
                if s.enabled and s.run_at >= now:
                    self.register_schedule(s.id, s.event_type, s.playlist_id, s.run_at, s.metadata_json)
                    count += 1
        logger.info("Synchronized %d upcoming schedule(s) from database into scheduler", count)
        return count


async def _run_playlist(schedule_id: int, playlist_id: int) -> None:
    """Execute a scheduled playlist, interrupt current if playing, and mark finished."""
    from database.session import SessionLocal
    from repositories.radio import RadioRepository
    from services.radio import RadioService
    async with SessionLocal() as session:
        try:
            service = RadioService(session)
            repo = RadioRepository(session)
            await service.run_playlist(playlist_id, actor="scheduler", interrupt_current=True)
            schedule = await repo.get_schedule(schedule_id)
            if schedule:
                schedule.enabled = False
                await session.commit()
            await service.emit_state()
            logger.info("Scheduled playlist executed and marked finished", extra={"schedule_id": schedule_id, "playlist_id": playlist_id})
        except Exception:
            logger.exception("Scheduled playlist execution failed", extra={"schedule_id": schedule_id, "playlist_id": playlist_id})


async def _run_news(schedule_id: int, metadata: dict[str, Any]) -> None:
    """Execute a scheduled news bulletin and mark finished."""
    from database.session import SessionLocal
    from repositories.radio import RadioRepository
    from services.radio import RadioService
    from tools.news_tool import NewsTool
    async with SessionLocal() as session:
        try:
            service = RadioService(session)
            repo = RadioRepository(session)
            duration = int(metadata.get("duration_seconds", 60))
            mix = metadata.get("mix", ["headlines", "weather", "station"])
            bulletin = await NewsTool.automatic_bulletin(duration, mix if isinstance(mix, list) else None)

            schedule = await repo.get_schedule(schedule_id)
            if schedule:
                schedule.metadata_json = {
                    **(schedule.metadata_json or {}),
                    **bulletin,
                    "broadcast_at": datetime.now(timezone.utc).isoformat(),
                }
                schedule.enabled = False
                await session.commit()

            state = await service.state()
            if state.status == "playing":
                await service.command("pause", actor="scheduler_news")
                asyncio.create_task(_resume_after_news(duration))

            await service.emit_state()
            logger.info("Scheduled news bulletin broadcasted and marked finished", extra={"schedule_id": schedule_id})
        except Exception:
            logger.exception("Scheduled news execution failed", extra={"schedule_id": schedule_id})


async def _resume_after_news(duration_seconds: int) -> None:
    """Resume music playback after news bulletin completes."""
    await asyncio.sleep(duration_seconds)
    from database.session import SessionLocal
    from services.radio import RadioService
    async with SessionLocal() as session:
        service = RadioService(session)
        state = await service.state()
        if state.status == "paused":
            await service.command("resume", actor="scheduler_news")


station_scheduler = StationScheduler()
