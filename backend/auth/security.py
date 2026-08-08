"""Password and JWT primitives."""

from datetime import datetime, timedelta, timezone
from typing import Any
import jwt
from pwdlib import PasswordHash

from core.config import settings

password_hash = PasswordHash.recommended()


def hash_password(password: str) -> str:
    """Hash a password using Argon2."""
    return password_hash.hash(password)


def verify_password(password: str, encoded: str) -> bool:
    """Verify a password against its hash."""
    return password_hash.verify(password, encoded)


def create_token(subject: str, token_type: str, lifespan: timedelta) -> str:
    """Issue a signed, expiration-bound JWT."""
    payload: dict[str, Any] = {"sub": subject, "type": token_type, "exp": datetime.now(timezone.utc) + lifespan}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_token_pair(email: str) -> tuple[str, str]:
    """Issue access and refresh tokens for an authenticated user."""
    return (
        create_token(email, "access", timedelta(minutes=settings.access_token_minutes)),
        create_token(email, "refresh", timedelta(days=settings.refresh_token_days)),
    )


def decode_access_token(token: str) -> str:
    """Validate an access token and return its user subject."""
    payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    if payload.get("type") != "access" or not payload.get("sub"):
        raise jwt.InvalidTokenError("Invalid token type")
    return str(payload["sub"])
