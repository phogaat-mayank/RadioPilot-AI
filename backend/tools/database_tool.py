"""Database-facing helper used by AI orchestration."""

from repositories.ai import AIRepository


class DatabaseTool:
    """Expose narrow AI persistence functions rather than raw sessions."""

    def __init__(self, repository: AIRepository) -> None:
        """Bind to the current AI repository."""
        self._repository = repository

    async def remember(self, namespace: str, key: str, value: dict) -> None:
        """Persist a durable learning observation."""
        await self._repository.upsert_memory(namespace, key, value)
