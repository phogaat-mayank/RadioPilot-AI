"""Application entry point for RadioPilot AI."""

from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from api.router import api_router
from core.config import settings
from core.logging import configure_logging
from core.rate_limit import limiter
from database.session import SessionLocal, close_database, initialize_database
from models.entities import StationMode
from repositories.radio import RadioRepository
from scheduler.service import station_scheduler
from services.bootstrap import bootstrap_station

configure_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Initialize infrastructure and graceful shutdown handlers."""
    await initialize_database()
    await bootstrap_station()
    station_scheduler.start()
    from autopilot.runtime import autopilot_runtime
    async with SessionLocal() as session:
        station = await RadioRepository(session).get_state()
        if station.mode is StationMode.AUTOPILOT:
            await autopilot_runtime.start()
    logger.info("RadioPilot AI started", extra={"environment": settings.environment})
    yield
    station_scheduler.shutdown()
    await autopilot_runtime.shutdown()
    await close_database()
    logger.info("RadioPilot AI stopped")


app = FastAPI(title=settings.app_name, version="1.0.0", lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(api_router, prefix="/api/v1")


@app.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    """Return a lightweight service health indicator."""
    return {"status": "healthy", "service": settings.app_name}
