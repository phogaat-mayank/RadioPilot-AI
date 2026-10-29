"""Tests for advanced RJ AI Chat Studio and LLM Gateway."""

import pytest
from agents.llm_gateway import LLMGateway
from repositories.ai import AIRepository
from models.entities import AIConversation
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from models.entities import Base


@pytest.mark.asyncio
async def test_llm_gateway_offline_fallback() -> None:
    """When offline or empty messages, fallback delivers intelligent guidance."""
    gateway = LLMGateway()
    resp = gateway._offline_response([{"role": "user", "content": "How do I create a playlist?"}])
    assert "playlist" in resp.lower()

    resp_general = gateway._offline_response([{"role": "user", "content": "What is the speed of light?"}])
    assert "RJ AI" in resp_general


@pytest.mark.asyncio
async def test_chat_history_repository() -> None:
    """Test persisting, retrieving, and clearing conversation history."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        repo = AIRepository(session)

        # Add messages
        await repo.add_message(AIConversation(session_id="test_sess", role="user", content="Hello RJ!"))
        await repo.add_message(AIConversation(session_id="test_sess", role="assistant", content="Hello! How can I assist?"))

        # Retrieve
        history = await repo.recent_messages("test_sess", limit=10)
        assert len(history) == 2
        assert history[0].role == "user"
        assert history[1].role == "assistant"

        # Clear
        deleted = await repo.clear_messages("test_sess")
        assert deleted == 2

        # Verify empty
        cleared = await repo.recent_messages("test_sess", limit=10)
        assert len(cleared) == 0

    await engine.dispose()
