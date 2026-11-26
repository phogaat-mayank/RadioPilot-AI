"""Tests for advanced RJ AI Chat Studio, LLM Gateway, and Nova Autonomous Station Actions."""

import pytest
from agents.llm_gateway import LLMGateway, _extract_text_tool_calls, strip_tool_markup
from repositories.ai import AIRepository
from models.entities import AIConversation, Song
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from models.entities import Base
from tools.nova_tools import detect_direct_station_intent, find_matching_song, find_matching_songs


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


@pytest.mark.asyncio
async def test_xml_tool_call_extraction_and_markup_stripping() -> None:
    """Leaked Qwen-style <tool_call> XML blocks are parsed cleanly and never shown raw to users."""
    leaked = (
        "<tool_call>\n"
        "<function=add_song_to_playlist>\n"
        "<parameter=playlist_name_or_id>\nCheema Y\n</parameter>\n"
        "<parameter=song_query>\nCartel - RaagWorld\n</parameter>\n"
        "</function>\n"
        "</tool_call>"
    )
    calls = _extract_text_tool_calls(leaked)
    assert calls == [
        ("add_song_to_playlist", {"playlist_name_or_id": "Cheema Y", "song_query": "Cartel - RaagWorld"})
    ]
    assert strip_tool_markup(leaked) == ""
    assert strip_tool_markup(f"Done!\n{leaked}") == "Done!"


@pytest.mark.asyncio
async def test_nova_batch_artist_match_and_add_all() -> None:
    """Adding all songs matching an artist in one tool call populates every matching track."""
    from models.entities import Playlist
    from repositories.radio import RadioRepository
    from tools.nova_tools import execute_nova_tool

    sample_songs = [
        Song(id=1, title="Shady - RaagWorld", artist="Cheema Y - RaagWorld", file_path="/app/media/s1.mp3"),
        Song(id=2, title="Cartel - RaagWorld", artist="Cheema Y - RaagWorld", file_path="/app/media/s2.mp3"),
        Song(id=3, title="Tension", artist="Dhanda Nyoliwala", file_path="/app/media/s3.mp3"),
    ]
    matches = find_matching_songs("Cheema Y", sample_songs)
    assert [s.id for s in matches] == [1, 2]

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        repo = RadioRepository(session)
        for title, artist, fp in [
            ("Shady - RaagWorld", "Cheema Y - RaagWorld", "/tmp/c1.mp3"),
            ("Cartel - RaagWorld", "Cheema Y - RaagWorld", "/tmp/c2.mp3"),
            ("Tension", "Dhanda Nyoliwala", "/tmp/d1.mp3"),
        ]:
            await repo.add_song(Song(title=title, artist=artist, file_path=fp))
        pl = await repo.add_playlist(Playlist(name="Cheema Y"))

        res = await execute_nova_tool(
            "add_song_to_playlist",
            {"playlist_name_or_id": "Cheema Y", "song_query": "Cheema Y", "add_all": True},
            session,
        )
        assert res["status"] == "added"
        assert set(res["added_songs"]) == {"Shady - RaagWorld", "Cartel - RaagWorld"}
        updated = await repo.get_playlist(pl.id)
        assert len(updated.items) == 2

    await engine.dispose()


@pytest.mark.asyncio
async def test_complete_agent_turn_executes_xml_and_never_leaks_markup(monkeypatch) -> None:
    """When a model leaks <tool_call> XML, complete_agent_turn executes it and returns clean text."""
    from core.config import settings
    import httpx

    monkeypatch.setattr(settings, "litellm_api_key", "gsk_test_key")
    monkeypatch.setattr(settings, "litellm_model", "groq/qwen/qwen3.8-27b")

    responses = [
        {
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": (
                        "<tool_call>\n<function=add_song_to_playlist>\n"
                        "<parameter=playlist_name_or_id>\nCheema Y\n</parameter>\n"
                        "<parameter=song_query>\nCartel - RaagWorld\n</parameter>\n"
                        "</function>\n</tool_call>"
                    ),
                }
            }]
        },
        {
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": "Added 'Cartel - RaagWorld' to playlist 'Cheema Y'!",
                }
            }]
        },
    ]
    seen_payloads: list[dict] = []

    class FakeResp:
        def __init__(self, body: dict) -> None:
            self.status_code = 200
            self._body = body
            self.text = ""
        def json(self) -> dict:
            return self._body

    class FakeClient:
        def __init__(self, *args, **kwargs) -> None:
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            return False
        async def post(self, url, headers=None, json=None):
            seen_payloads.append(json)
            return FakeResp(responses.pop(0))

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)

    executed: list[tuple[str, dict]] = []
    async def fake_exec(name: str, args: dict) -> dict:
        executed.append((name, args))
        return {"status": "added", "message": "Added 'Cartel - RaagWorld' to playlist 'Cheema Y'."}

    reply, model, actions = await LLMGateway().complete_agent_turn(
        "You are NOVA",
        [{"role": "user", "content": "add cartel"}],
        tools=[{"type": "function", "function": {"name": "add_song_to_playlist", "parameters": {}}}],
        tool_executor=fake_exec,
    )
    assert len(executed) == 1
    assert executed[0][0] == "add_song_to_playlist"
    assert executed[0][1]["song_query"] == "Cartel - RaagWorld"
    assert "<tool_call" not in reply
    assert "Cartel - RaagWorld" in reply
    # Tools remained available on turn 2 too!
    assert "tools" in seen_payloads[0]
    assert "tools" in seen_payloads[1]
