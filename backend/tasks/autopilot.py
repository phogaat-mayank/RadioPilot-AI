"""Hourly multi-agent autopilot workflow."""

import asyncio
import logging
from celery import shared_task
from database.session import SessionLocal
from models.entities import StationMode
from repositories.radio import RadioRepository
from schemas.ai import AIRequest
from services.ai import AIService

logger = logging.getLogger(__name__)


async def run_hourly_cycle() -> dict:
    """Run the hourly plan only when AI owns station decisions."""
    async with SessionLocal() as session:
        if (await RadioRepository(session).get_state()).mode != StationMode.AUTOPILOT:
            return {"status": "skipped", "reason": "manual mode"}
        service = AIService(session)
        results = []
        for action, prompt in [("schedule", "Check the upcoming hourly schedule and fill valid empty slots."), ("playlist", "Create the next hour music rotation."), ("script", "Create a concise top-of-hour RJ transition."), ("news", "Prepare the hourly news bulletin from verified headlines."), ("ads", "Place an advertiser-balanced, non-consecutive ad break.")]:
            result = await service.execute(action, AIRequest(prompt=prompt, duration_minutes=60), "celery-autopilot")
            results.append({"action": action, "task_id": result.task_id})
        return {"status": "completed", "tasks": results}


@shared_task(name="tasks.autopilot.hourly_autopilot")
def hourly_autopilot() -> dict:
    """Celery entry point for the hourly autopilot cycle."""
    try:
        return asyncio.run(run_hourly_cycle())
    except Exception as error:
        logger.exception("Hourly autopilot failed")
        raise error
