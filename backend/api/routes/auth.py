"""Authentication endpoints."""

from datetime import timedelta
import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import UserDep
from auth.security import create_token_pair, verify_password
from core.config import settings
from core.rate_limit import limiter
from database.session import get_session
from repositories.radio import RadioRepository
from schemas.radio import LoginRequest, RefreshTokenRequest, TokenPair, UserOut

router = APIRouter(prefix="/auth", tags=["authentication"])


@router.post("/login", response_model=TokenPair)
@limiter.limit("10/minute")
async def login(request: Request, payload: LoginRequest, session: AsyncSession = Depends(get_session)) -> TokenPair:
    """Authenticate a user and issue rotation-ready token pair."""
    user = await RadioRepository(session).find_user(payload.email)
    if not user or not user.is_active or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    access, refresh = create_token_pair(user.email)
    return TokenPair(access_token=access, refresh_token=refresh)


@router.get("/me", response_model=UserOut)
async def me(user: UserDep) -> UserOut:
    """Return the currently authenticated operator profile."""
    role_str = user.role.value if hasattr(user.role, "value") else str(user.role)
    return UserOut(id=user.id, email=user.email, role=role_str, is_active=user.is_active)


@router.post("/refresh", response_model=TokenPair)
async def refresh_session(payload: RefreshTokenRequest, session: AsyncSession = Depends(get_session)) -> TokenPair:
    """Exchange a valid refresh token for a fresh token pair."""
    try:
        raw_payload = jwt.decode(payload.refresh_token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        if raw_payload.get("type") != "refresh" or not raw_payload.get("sub"):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token type")
        email = str(raw_payload["sub"])
    except jwt.PyJWTError as err:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Expired or invalid refresh token") from err

    user = await RadioRepository(session).find_user(email)
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User account is inactive or missing")

    access, refresh = create_token_pair(user.email)
    return TokenPair(access_token=access, refresh_token=refresh)

