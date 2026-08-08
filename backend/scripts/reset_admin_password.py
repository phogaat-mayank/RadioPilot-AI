"""Reset the configured administrator account from environment settings."""

import asyncio

from auth.security import hash_password
from core.config import settings
from database.session import SessionLocal
from models.entities import User, UserRole
from repositories.radio import RadioRepository


async def reset_admin_password() -> None:
    """Create or update the configured administrator without deleting station data."""
    async with SessionLocal() as session:
        repository = RadioRepository(session)
        user = await repository.find_user(settings.admin_email)
        if user is None:
            await repository.add_user(User(email=settings.admin_email.lower(), password_hash=hash_password(settings.admin_password), role=UserRole.ADMIN))
        else:
            user.password_hash = hash_password(settings.admin_password)
            user.is_active = True
            await session.commit()
    print(f"Administrator password reset for {settings.admin_email}")


if __name__ == "__main__":
    asyncio.run(reset_admin_password())
