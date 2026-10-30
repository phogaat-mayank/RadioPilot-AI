"""First-run station initialization."""

from database.session import SessionLocal
from auth.security import hash_password
from models.entities import User, UserRole
from repositories.radio import RadioRepository


async def bootstrap_station() -> None:
    """Create station state and configured administrator once."""
    from core.config import settings
    async with SessionLocal() as session:
        repository = RadioRepository(session)
        await repository.get_state()
        if not await repository.find_user(settings.admin_email):
            await repository.add_user(User(email=settings.admin_email.lower(), password_hash=hash_password(settings.admin_password), role=UserRole.ADMIN))
        from scheduler.service import station_scheduler
        await station_scheduler.sync_database_schedules()
