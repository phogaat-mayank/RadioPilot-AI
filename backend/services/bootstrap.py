"""First-run station initialization."""

import logging
from pathlib import Path
from sqlalchemy import select

from api.routes.library import detect_audio_duration
from database.session import SessionLocal
from auth.security import hash_password
from models.entities import Song, User, UserRole
from repositories.radio import RadioRepository

logger = logging.getLogger(__name__)


async def bootstrap_station() -> None:
    """Create station state, backfill missing audio durations, and register schedules."""
    from core.config import settings
    async with SessionLocal() as session:
        repository = RadioRepository(session)
        await repository.get_state()
        if not await repository.find_user(settings.admin_email):
            await repository.add_user(User(email=settings.admin_email.lower(), password_hash=hash_password(settings.admin_password), role=UserRole.ADMIN))

        # Backfill duration for library songs uploaded before multi-format duration detection
        zero_duration_songs = (await session.scalars(select(Song).where(Song.duration_seconds <= 0))).all()
        updated = 0
        for song in zero_duration_songs:
            path = Path(song.file_path)
            if path.is_file():
                duration = detect_audio_duration(path)
                if duration > 0:
                    song.duration_seconds = duration
                    updated += 1
        if updated:
            await session.commit()
            logger.info("Backfilled duration_seconds for %d existing library song(s)", updated)

        from scheduler.service import station_scheduler
        await station_scheduler.sync_database_schedules()
