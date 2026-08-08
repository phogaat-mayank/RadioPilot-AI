"""Authentication endpoints."""

from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from auth.security import create_token_pair, verify_password
from core.config import settings
from core.rate_limit import limiter
from database.session import get_session
from repositories.radio import RadioRepository
from schemas.radio import LoginRequest, TokenPair

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
