"""Reusable authenticated endpoint dependencies."""

from typing import Annotated
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from auth.security import decode_access_token
from database.session import get_session
from models.entities import User, UserRole
from repositories.radio import RadioRepository

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")
SessionDep = Annotated[AsyncSession, Depends(get_session)]


async def current_user(token: Annotated[str, Depends(oauth2_scheme)], session: SessionDep) -> User:
    """Resolve and validate the active user from a bearer token."""
    try:
        email = decode_access_token(token)
    except jwt.PyJWTError as error:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token") from error
    user = await RadioRepository(session).find_user(email)
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User is inactive or unavailable")
    return user


UserDep = Annotated[User, Depends(current_user)]


def require_roles(*roles: UserRole):
    """Build a dependency enforcing role-based access control."""
    async def checker(user: UserDep) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")
        return user
    return checker
