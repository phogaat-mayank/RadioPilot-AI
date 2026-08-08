"""Repository for AI tasks, memory, conversations, and decisions."""

from collections.abc import Sequence
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from models.entities import AIConversation, AIDecision, AILog, AIMemory, AITask


class AIRepository:
    """Keep AI persistence mechanics outside agent and API code."""

    def __init__(self, session: AsyncSession) -> None:
        """Bind the repository to an injected unit of work."""
        self.session = session

    async def create_task(self, task: AITask) -> AITask:
        """Persist a queued AI task."""
        self.session.add(task)
        await self.session.commit()
        await self.session.refresh(task)
        return task

    async def log(self, log: AILog) -> None:
        """Persist an AI event."""
        self.session.add(log)
        await self.session.commit()

    async def add_message(self, message: AIConversation) -> None:
        """Persist one chat message."""
        self.session.add(message)
        await self.session.commit()

    async def recent_messages(self, session_id: str, limit: int = 12) -> Sequence[AIConversation]:
        """Return recent messages in chronological order."""
        records = (await self.session.scalars(select(AIConversation).where(AIConversation.session_id == session_id).order_by(AIConversation.created_at.desc()).limit(limit))).all()
        return list(reversed(records))

    async def upsert_memory(self, namespace: str, key: str, value: dict) -> AIMemory:
        """Write durable AI memory using a namespaced key."""
        memory = await self.session.scalar(select(AIMemory).where(AIMemory.namespace == namespace, AIMemory.memory_key == key))
        if memory is None:
            memory = AIMemory(namespace=namespace, memory_key=key, value_json=value)
            self.session.add(memory)
        else:
            memory.value_json = value
        await self.session.commit()
        await self.session.refresh(memory)
        return memory

    async def create_decision(self, decision: AIDecision) -> AIDecision:
        """Persist an approval-gated recommendation."""
        self.session.add(decision)
        await self.session.commit()
        await self.session.refresh(decision)
        return decision

    async def update_decision(self, decision_id: int, status: str, approver: str) -> AIDecision | None:
        """Store a decisive RJ action on a proposed recommendation."""
        decision = await self.session.get(AIDecision, decision_id)
        if decision is None:
            return None
        decision.status, decision.approved_by = status, approver
        await self.session.commit()
        await self.session.refresh(decision)
        return decision

    async def pending_decisions(self) -> int:
        """Count approval-gated recommendations."""
        return len((await self.session.scalars(select(AIDecision).where(AIDecision.status == "proposed"))).all())

    async def history(self, limit: int = 100) -> Sequence[AITask]:
        """Return recent AI task history."""
        return (await self.session.scalars(select(AITask).order_by(AITask.created_at.desc()).limit(limit))).all()
