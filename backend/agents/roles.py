"""Pure decision agents; none invoke the playback controller."""

from typing import TypedDict


class Recommendation(TypedDict):
    """Constrained agent output passed to the service layer for validation."""
    action: str
    rationale: str
    song_id: int | None


def scheduler_agent(_: dict) -> Recommendation:
    """Recommend no immediate schedule change without an eligible trigger."""
    return {"action": "monitor", "rationale": "No due schedule requires intervention", "song_id": None}


def playlist_agent(context: dict) -> Recommendation:
    """Recommend the first available queued song when station is idle."""
    queue = context.get("queue", [])
    return {"action": "play_next" if queue else "monitor", "rationale": "Queue availability assessed", "song_id": queue[0] if queue else None}


def playback_agent(recommendation: Recommendation) -> Recommendation:
    """Review a recommendation without executing it."""
    return recommendation


def broadcast_agent(recommendation: Recommendation) -> Recommendation:
    """Apply broadcast-policy framing to a recommendation."""
    return recommendation


def monitoring_agent(recommendation: Recommendation) -> Recommendation:
    """Return the recommendation for supervisor audit."""
    return recommendation


def assistant_agent(prompt: str) -> str:
    """Provide a deterministic safe assistant acknowledgement without audio control."""
    return f"Station assistant received: {prompt.strip()[:300]}"
