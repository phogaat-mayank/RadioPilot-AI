"""Pydantic contracts for the multi-agent AI platform."""

from datetime import datetime
from typing import Any, Literal
from pydantic import BaseModel, Field

AIAction = Literal["chat", "schedule", "playlist", "script", "news", "ads", "analyze", "autopilot"]


class AIRequest(BaseModel):
    """Generic request accepted by RJ AI and specialist routes."""
    prompt: str = Field(min_length=1, max_length=4000)
    session_id: str = Field(default="default", max_length=80)
    mood: str | None = Field(default=None, max_length=80)
    duration_minutes: int | None = Field(default=None, ge=1, le=1440)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AIResponse(BaseModel):
    """Auditable specialist-agent result."""
    task_id: int
    agent: str
    status: str
    response: str
    data: dict[str, Any] = Field(default_factory=dict)
    requires_approval: bool = False


class AIStatus(BaseModel):
    """Operational AI mode and queue summary."""
    mode: str
    autopilot_enabled: bool
    pending_approvals: int
    last_task_at: datetime | None = None


class AIDecisionUpdate(BaseModel):
    """RJ approval or rejection payload."""
    approved: bool
