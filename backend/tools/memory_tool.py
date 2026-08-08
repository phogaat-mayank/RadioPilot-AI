"""Memory-key conventions for durable agent learning."""

from datetime import datetime, timezone

class MemoryTool:
    """Create stable keys and values for AI decision recall."""

    @staticmethod
    def decision_value(agent: str, request_type: str, outcome: dict) -> tuple[str, dict]:
        """Package a decision into a predictable memory entry."""
        timestamp = datetime.now(timezone.utc).isoformat()
        return f"{request_type}:{timestamp}", {"agent": agent, "outcome": outcome, "recorded_at": timestamp}
