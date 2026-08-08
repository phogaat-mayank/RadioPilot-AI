"""APScheduler coordinator for scheduled broadcast events."""

from datetime import datetime, timezone
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler

logger = logging.getLogger(__name__)


class StationScheduler:
    """Own APScheduler lifecycle and dispatch only validated station work."""

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

    def register_playlist(self, schedule_id: int, playlist_id: int, run_at: datetime) -> None:
        """Register a one-time playlist job that routes through the service layer."""
        timestamp = run_at.astimezone(timezone.utc) if run_at.tzinfo else run_at.replace(tzinfo=timezone.utc)
        self._scheduler.add_job(_run_playlist, "date", run_date=timestamp, args=[playlist_id], id=f"schedule-{schedule_id}", replace_existing=True, misfire_grace_time=300)


async def _run_playlist(playlist_id: int) -> None:
    """Open a short-lived database unit of work for a scheduled playlist."""
    from database.session import SessionLocal
    from models.entities import StationMode
    from repositories.radio import RadioRepository
    from services.radio import RadioService
    async with SessionLocal() as session:
        try:
            if (await RadioRepository(session).get_state()).mode is StationMode.AUTOPILOT:
                logger.info("Legacy scheduler deferred playlist execution to autopilot", extra={"playlist_id": playlist_id})
                return
            await RadioService(session).run_playlist(playlist_id)
        except Exception:
            logger.exception("Scheduled playlist execution failed", extra={"playlist_id": playlist_id})


station_scheduler = StationScheduler()
