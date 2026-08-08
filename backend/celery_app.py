"""Celery application for durable background AI automation."""

from celery import Celery
from core.config import settings

celery_app = Celery("radiopilot", broker=settings.celery_broker_url, backend=settings.celery_result_backend, include=["tasks.autopilot"])
celery_app.conf.update(timezone="UTC", enable_utc=True, task_track_started=True, beat_schedule={"hourly-radio-autopilot": {"task": "tasks.autopilot.hourly_autopilot", "schedule": 3600.0}})
