"""Tests for Piper TTS engine, voice models, AI DJ announcements, and playback sequencing."""

import pytest
from schemas.radio import AIDJSettingsOut, AnnouncementOut
from services.dj_voice_service import dj_voice_service
from services.tts_service import SUPPORTED_VOICES, tts_service


def test_supported_voices_catalog():
    """Verify that all 4 real Piper voice models exist in the catalog with licenses."""
    voices = tts_service.get_supported_voices()
    assert len(voices) == 4
    voice_ids = {v["id"] for v in voices}
    assert "hi_IN-priyamvada-medium" in voice_ids
    assert "hi_IN-pratham-medium" in voice_ids
    assert "en_US-lessac-medium" in voice_ids
    assert "en_US-ryan-medium" in voice_ids

    for v in voices:
        assert v["license"]
        assert v["sample_rate"] == 22050
        assert v["language_code"] in {"hi_IN", "en_US"}


@pytest.mark.asyncio
async def test_synthesis_hindi_voice():
    """Verify real local Hindi speech synthesis with Piper."""
    text = "नमस्ते दोस्तों! रेडियो पायलट एआई पर आपका स्वागत है।"
    audio = await tts_service.synthesize(text, voice_id="hi_IN-priyamvada-medium")
    assert audio.id.startswith("ann_")
    assert audio.duration_seconds > 0.5
    assert audio.file_size_bytes > 1000
    assert audio.voice_id == "hi_IN-priyamvada-medium"


@pytest.mark.asyncio
async def test_synthesis_english_voice():
    """Verify real local English speech synthesis with Piper."""
    text = "Hello listeners! You are tuned into RadioPilot AI on air."
    audio = await tts_service.synthesize(text, voice_id="en_US-lessac-medium")
    assert audio.id.startswith("ann_")
    assert audio.duration_seconds > 0.5
    assert audio.file_size_bytes > 1000
    assert audio.voice_id == "en_US-lessac-medium"


def test_dj_script_composition():
    """Verify natural intro and outro composition in Hindi and English."""
    hi_intro = dj_voice_service.compose_intro_script("Kesariya", "Arijit Singh", language="hi")
    assert "Kesariya" in hi_intro
    assert "Arijit Singh" in hi_intro
    assert "रेडियोपायलट" in hi_intro

    en_intro = dj_voice_service.compose_intro_script("Blinding Lights", "The Weeknd", language="en")
    assert "Blinding Lights" in en_intro
    assert "The Weeknd" in en_intro
    assert "RadioPilot" in en_intro

    hi_outro = dj_voice_service.compose_outro_script("Kesariya", "Arijit Singh", language="hi")
    assert "Kesariya" in hi_outro


@pytest.mark.asyncio
async def test_advance_announcement_preparation():
    """Verify advance announcement preparation and consumption."""
    settings = AIDJSettingsOut(
        enabled=True,
        voice_id="en_US-lessac-medium",
        language="en",
        frequency=1,
        volume=100,
        intro_enabled=True,
        outro_enabled=False,
        greeting_enabled=True,
    )

    ann = await dj_voice_service.prepare_next_announcement(
        next_song_title="Shape of You",
        next_song_artist="Ed Sheeran",
        settings=settings,
    )
    assert ann is not None
    assert "Shape of You" in ann.text

    # Consume announcement
    consumed = await dj_voice_service.get_and_consume_announcement(settings)
    assert consumed is not None
    assert consumed.id == ann.id

    # Consuming again before next song returns None
    consumed_again = await dj_voice_service.get_and_consume_announcement(settings)
    assert consumed_again is None


@pytest.mark.asyncio
async def test_tts_disabled_fallback():
    """When AI DJ is disabled, no announcement is prepared or returned."""
    settings = AIDJSettingsOut(
        enabled=False,
        voice_id="en_US-lessac-medium",
        language="en",
        frequency=1,
        volume=100,
    )

    ann = await dj_voice_service.prepare_next_announcement(
        next_song_title="Test Song",
        next_song_artist="Test Artist",
        settings=settings,
    )
    assert ann is None

    consumed = await dj_voice_service.get_and_consume_announcement(settings)
    assert consumed is None
