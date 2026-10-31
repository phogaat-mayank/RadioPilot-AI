"""End-to-End integration tests for the AI DJ Voice Engine in RadioPilot AI.

Validates:
1. Hindi voice generation (Priyamvada & Pratham).
2. English voice generation (Lessac & Ryan).
3. Test Voice preview API endpoint.
4. Manual announcements broadcasting.
5. Autopilot track -> announcement -> next track sequencing (no overlap).
6. Failure fallback and graceful recovery.
"""

import io
import wave
import pytest
from httpx import ASGITransport, AsyncClient

from main import app
from auth.security import create_token_pair
from database.session import SessionLocal
from models.entities import Song, AIDJSettings
from playback.controller import playback_controller
from services.dj_voice_service import dj_voice_service
from services.radio import RadioService
from services.tts_service import tts_service
from sqlalchemy import select


@pytest.fixture
def auth_token() -> str:
    access_token, _ = create_token_pair("admin@radiopilot.local")
    return access_token


@pytest.mark.asyncio
async def test_all_four_voices_synthesize_valid_wav():
    """Verify all 4 verified Piper models synthesize genuine 22050Hz 16-bit PCM WAV audio."""
    voices = [
        ("hi_IN-priyamvada-medium", "नमस्ते! रेडियोपायलट एआई पर आपका स्वागत है।"),
        ("hi_IN-pratham-medium", "यह है रेडियोपायलट एआई, बेहतरीन संगीत के साथ।"),
        ("en_US-lessac-medium", "Welcome to RadioPilot AI, broadcasting commercial free."),
        ("en_US-ryan-medium", "You're listening to RadioPilot AI on air."),
    ]

    for voice_id, sample_text in voices:
        audio = await tts_service.synthesize(sample_text, voice_id=voice_id)
        assert audio.id.startswith("ann_")
        assert audio.duration_seconds > 0.4
        assert audio.file_size_bytes > 500

        # Read the file and verify valid WAV container structure
        with wave.open(audio.file_path, "rb") as wf:
            assert wf.getnchannels() == 1
            assert wf.getsampwidth() == 2  # 16-bit
            assert wf.getframerate() == 22050
            frames = wf.getnframes()
            assert frames > 0


@pytest.mark.asyncio
async def test_preview_endpoint_test_voice(auth_token: str):
    """Test Voice button uses POST /api/v1/tts/preview to stream audition audio without affecting broadcast."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Test English voice preview
        res_en = await client.post(
            "/api/v1/tts/preview",
            headers={"Authorization": f"Bearer {auth_token}"},
            json={
                "text": "Auditioning English voice model.",
                "voice_id": "en_US-lessac-medium",
                "language": "en",
            },
        )
        assert res_en.status_code == 200
        assert res_en.headers["content-type"] == "audio/wav"
        assert res_en.content[:4] == b"RIFF"

        # Test Hindi voice preview
        res_hi = await client.post(
            "/api/v1/tts/preview",
            headers={"Authorization": f"Bearer {auth_token}"},
            json={
                "text": "नमस्ते! यह आवाज़ का परीक्षण है।",
                "voice_id": "hi_IN-priyamvada-medium",
                "language": "hi",
            },
        )
        assert res_hi.status_code == 200
        assert res_hi.headers["content-type"] == "audio/wav"
        assert res_hi.content[:4] == b"RIFF"


@pytest.mark.asyncio
async def test_manual_announcement_workflow(auth_token: str):
    """Verify manual announcement broadcasting and lifecycle."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Trigger manual announcement with play_immediately=True
        ann_text = "Breaking update: Live studio announcement on RadioPilot AI."
        res = await client.post(
            "/api/v1/tts/manual-announcement",
            headers={"Authorization": f"Bearer {auth_token}"},
            json={
                "text": ann_text,
                "voice_id": "en_US-ryan-medium",
                "language": "en",
                "play_immediately": True,
            },
        )
        assert res.status_code == 200
        ann_data = res.json()
        ann_id = ann_data["id"]
        assert ann_data["text"] == ann_text

        # 2. Check station status - active_announcement must be set
        status_res = await client.get(
            "/api/v1/station/status",
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert status_res.status_code == 200
        status = status_res.json()
        assert status["active_announcement"] is not None
        assert status["active_announcement"]["id"] == ann_id

        # 3. Stream the announcement audio
        stream_res = await client.get(
            f"/api/v1/tts/stream/{ann_id}",
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert stream_res.status_code == 200
        assert stream_res.headers["content-type"] == "audio/wav"
        assert stream_res.content[:4] == b"RIFF"

        # 4. Announcement finishes playing in player -> calls /station/announcement-ended
        ended_res = await client.post(
            "/api/v1/station/announcement-ended",
            headers={"Authorization": f"Bearer {auth_token}"},
            json={"announcement_id": ann_id, "playback_revision": 1},
        )
        assert ended_res.status_code == 200
        ended_status = ended_res.json()
        # active_announcement must be cleared!
        assert ended_status["active_announcement"] is None


@pytest.mark.asyncio
async def test_autopilot_song_announcement_next_song_sequence():
    """Verify strictly sequential playback:
    Song 1 finishes -> Announcement plays -> Announcement finishes -> Song 2 plays.
    Never overlapping streams.
    """
    async with SessionLocal() as session:
        # Ensure songs exist in library
        stmt = select(Song).limit(2)
        res = await session.execute(stmt)
        songs = res.scalars().all()
        if len(songs) < 2:
            pytest.skip("Test requires at least 2 songs in DB")

        song1, song2 = songs[0], songs[1]

        # Ensure AI DJ settings have frequency=1 and intros enabled
        dj_stmt = select(AIDJSettings).where(AIDJSettings.id == 1)
        dj_res = await session.execute(dj_stmt)
        dj_settings = dj_res.scalar_one_or_none()
        if not dj_settings:
            dj_settings = AIDJSettings(id=1, enabled=True, frequency_songs=1)
            session.add(dj_settings)
        else:
            dj_settings.enabled = True
            dj_settings.frequency_songs = 1
            dj_settings.intros_enabled = True
            session.add(dj_settings)
        await session.commit()

        radio = RadioService(session)

        # Setup queue: [song2] and start song1
        await playback_controller.clear_queue()
        await radio.enqueue_song(song2.id, "test_operator")
        await radio.play(song1.id, "test_operator")

        state1 = await radio.emit_state()
        assert state1.current_song is not None
        assert state1.current_song.id == song1.id
        assert state1.active_announcement is None

        # Pre-generate announcement in advance for the upcoming song2
        ann = await dj_voice_service.prepare_next_announcement(
            next_song_title=song2.title,
            next_song_artist=song2.artist,
            settings=dj_settings,
        )
        assert ann is not None

        # Song 1 finishes playing -> triggers track_ended
        state_after_song1 = await radio.track_ended(state1.playback_revision, "browser_player")

        # Must deliver the AI DJ announcement!
        assert state_after_song1.active_announcement is not None
        assert state_after_song1.active_announcement.id == ann.id

        # Announcement is now playing in browser's single audio element.
        # Announcement finishes playing -> triggers announcement_ended
        state_after_ann = await radio.announcement_ended(state_after_song1.playback_revision, "browser_player")

        # Active announcement cleared! Next song started!
        assert state_after_ann.active_announcement is None
        assert state_after_ann.current_song is not None
        assert state_after_ann.current_song.id == song2.id
        assert state_after_ann.status == "playing"

        await playback_controller.stop()
        await playback_controller.clear_queue()
        import asyncio
        await asyncio.sleep(1.2)


@pytest.mark.asyncio
async def test_tts_failure_fallback_graceful_recovery():
    """Verify that if TTS fails or is disabled, track_ended proceeds immediately to next song."""
    async with SessionLocal() as session:
        stmt = select(Song).limit(2)
        res = await session.execute(stmt)
        songs = res.scalars().all()
        if len(songs) < 2:
            pytest.skip("Test requires at least 2 songs in DB")

        song1, song2 = songs[0], songs[1]

        # Disable AI DJ in settings
        dj_stmt = select(AIDJSettings).where(AIDJSettings.id == 1)
        dj_res = await session.execute(dj_stmt)
        dj_settings = dj_res.scalar_one_or_none()
        if dj_settings:
            dj_settings.enabled = False
            session.add(dj_settings)
            await session.commit()

        radio = RadioService(session)
        await playback_controller.clear_queue()
        await radio.enqueue_song(song2.id, "test_operator")
        await radio.play(song1.id, "test_operator")

        state = await radio.emit_state()
        rev = state.playback_revision

        # Track finishes with TTS disabled
        next_state = await radio.track_ended(rev, "browser_player")

        # Seamlessly advances directly to song2 without any announcement delay or error
        assert next_state.active_announcement is None
        assert next_state.current_song is not None
        assert next_state.current_song.id == song2.id

        await playback_controller.stop()
        await playback_controller.clear_queue()
        import asyncio
        await asyncio.sleep(1.2)
