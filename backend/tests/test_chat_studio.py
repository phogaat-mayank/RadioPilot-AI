"""Tests for advanced RJ AI Chat Studio, LLM Gateway, and Nova Autonomous Station Actions."""

import pytest
from agents.llm_gateway import LLMGateway
from repositories.ai import AIRepository
from models.entities import AIConversation, Song
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from models.entities import Base
from tools.nova_tools import detect_direct_station_intent, find_matching_song


@pytest.mark.asyncio
async def test_llm_gateway_offline_fallback() -> None:
    """When offline or empty messages, fallback delivers intelligent guidance."""
    gateway = LLMGateway()
    resp = gateway._offline_response([{"role": "user", "content": "How do I create a playlist?"}])
    assert "playlist" in resp.lower()

    resp_general = gateway._offline_response([{"role": "user", "content": "What is the speed of light?"}])
    assert "RJ AI" in resp_general


@pytest.mark.asyncio
async def test_nova_song_matching() -> None:
    """Nova can match songs in English and Hindi transliteration."""
    sample_songs = [
        Song(id=1, title="Shady - RaagWorld", artist="Cheema Y - RaagWorld", file_path="/app/media/s1.mp3"),
        Song(id=2, title="Yaari On Top", artist="Sumit Goswami", file_path="/app/media/s2.mp3"),
        Song(id=3, title="Tension", artist="Dhanda Nyoliwala", file_path="/app/media/s3.mp3"),
    ]
    # English title match
    s1 = find_matching_song("Shady", sample_songs)
    assert s1 is not None and s1.id == 1

    # Artist match
    s2 = find_matching_song("Sumit Goswami", sample_songs)
    assert s2 is not None and s2.id == 2

    # Hindi transliteration match ("शेडी" -> "shady")
    s3 = find_matching_song("शेडी", sample_songs)
    assert s3 is not None and s3.id == 1


@pytest.mark.asyncio
async def test_nova_direct_intent_detection() -> None:
    """Nova directly detects common station commands for instant execution."""
    assert detect_direct_station_intent("start autopilot") == ("set_autopilot", {"enabled": True})
    assert detect_direct_station_intent("manual mode") == ("set_autopilot", {"enabled": False})
    assert detect_direct_station_intent("pause music") == ("control_playback", {"action": "pause"})
    assert detect_direct_station_intent("skip") == ("control_playback", {"action": "skip"})
    assert detect_direct_station_intent("volume 75") == ("set_volume", {"level": 75})
    assert detect_direct_station_intent("station status") == ("get_station_status", {})
    assert detect_direct_station_intent("play Shady") == ("play_song", {"song_query": "shady"})


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
