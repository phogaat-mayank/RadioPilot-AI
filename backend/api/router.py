"""Versioned API route aggregation."""

from fastapi import APIRouter
from api.routes import ai, auth, library, playlists, schedules, station

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(library.router)
api_router.include_router(playlists.router)
api_router.include_router(schedules.router)
api_router.include_router(station.router)
api_router.include_router(ai.router)
