"""Endpoints for Piper TTS voice synthesis, settings, and audio streaming."""

from __future__ import annotations

import logging
from pathlib import Path
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy import select

from api.deps import SessionDep, UserDep
from models.entities import AIDJSettings
from schemas.radio import (
    AIDJSettingsOut,
    AIDJSettingsUpdate,
    AnnouncementOut,
    ManualAnnouncementRequest,
    TTSSynthesizeRequest,
    TTSVoiceOut,
)
from services.dj_voice_service import dj_voice_service
from services.radio import RadioService
from services.tts_service import SUPPORTED_VOICES, tts_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tts", tags=["piper tts voice engine"])


@router.get("/voices", response_model=list[TTSVoiceOut])
async def list_voices(_: UserDep) -> list[TTSVoiceOut]:
    """Return all verified real Piper voice models and their local availability."""
    voices = tts_service.get_supported_voices()
    return [TTSVoiceOut(**v) for v in voices]


@router.get("/settings", response_model=AIDJSettingsOut)
async def get_settings(session: SessionDep, _: UserDep) -> AIDJSettingsOut:
    """Retrieve the persistent AI DJ voice configuration."""
    stmt = select(AIDJSettings).where(AIDJSettings.id == 1)
    result = await session.execute(stmt)
    settings_obj = result.scalar_one_or_none()

    if not settings_obj:
        settings_obj = AIDJSettings(
            id=1,
            enabled=True,
            voice_id="hi_IN-priyamvada-medium",
            language="hi",
            frequency=1,
            volume=100,
            intro_enabled=True,
            outro_enabled=False,
            greeting_enabled=True,
        )
        session.add(settings_obj)
        await session.commit()
        await session.refresh(settings_obj)

    return AIDJSettingsOut.model_validate(settings_obj)


@router.put("/settings", response_model=AIDJSettingsOut)
async def update_settings(
    payload: AIDJSettingsUpdate,
    session: SessionDep,
    user: UserDep,
) -> AIDJSettingsOut:
    """Update and persist AI DJ voice configuration."""
    stmt = select(AIDJSettings).where(AIDJSettings.id == 1)
    result = await session.execute(stmt)
    settings_obj = result.scalar_one_or_none()

    if not settings_obj:
        settings_obj = AIDJSettings(id=1)
        session.add(settings_obj)

    update_data = payload.model_dump(exclude_unset=True)
    if "voice_id" in update_data and update_data["voice_id"] not in SUPPORTED_VOICES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid voice_id. Choose from: {list(SUPPORTED_VOICES.keys())}",
        )

    for field, value in update_data.items():
        setattr(settings_obj, field, value)

    await session.commit()
    await session.refresh(settings_obj)

    await RadioService(session).log(
        "voice",
        f"AI DJ settings updated by {user.email}",
        user.email,
        update_data,
    )

    return AIDJSettingsOut.model_validate(settings_obj)


@router.post("/synthesize", response_model=AnnouncementOut)
async def synthesize_text(
    payload: TTSSynthesizeRequest,
    session: SessionDep,
    user: UserDep,
) -> AnnouncementOut:
    """Synthesize custom announcement text using the specified or default voice."""
    voice_id = payload.voice_id
    if not voice_id:
        stmt = select(AIDJSettings).where(AIDJSettings.id == 1)
        res = await session.execute(stmt)
        s = res.scalar_one_or_none()
        voice_id = s.voice_id if s else "hi_IN-priyamvada-medium"

    try:
        audio = await tts_service.synthesize(payload.text, voice_id=voice_id)
        return AnnouncementOut(
            id=audio.id,
            text=audio.text,
            voice_id=audio.voice_id,
            duration_seconds=audio.duration_seconds,
            stream_url=f"/tts/stream/{audio.id}",
            announcement_type="custom",
        )
    except Exception as exc:
        logger.exception("Synthesis error: %s", exc)
        raise HTTPException(status_code=500, detail=f"TTS synthesis failed: {exc}") from exc


@router.post("/preview")
async def preview_voice(
    payload: TTSSynthesizeRequest | None = None,
    voice_id: str | None = Query(default=None),
    _: UserDep = None,
) -> FileResponse:
    """Generate an instant voice audition sample for the Test Voice button."""
    selected_voice = (payload.voice_id if payload and payload.voice_id else None) or voice_id
    if not selected_voice or selected_voice not in SUPPORTED_VOICES:
        raise HTTPException(status_code=400, detail="Invalid or missing voice_id")

    meta = SUPPORTED_VOICES[selected_voice]
    text = (payload.text if payload and payload.text else None) or (
        "रेडियोपायलट एआई में आपका स्वागत है। यह आपकी नई एआई डीजे आवाज है!"
        if meta["language_code"].startswith("hi")
        else "Welcome to RadioPilot AI. This is your new on-air voice preview!"
    )

    try:
        audio = await tts_service.synthesize(text, voice_id=selected_voice)
        return FileResponse(audio.file_path, media_type="audio/wav", filename=f"preview_{selected_voice}.wav")
    except Exception as exc:
        logger.exception("Preview synthesis error: %s", exc)
        raise HTTPException(status_code=500, detail=f"Voice test synthesis failed: {exc}") from exc


@router.post("/manual-announcement", response_model=AnnouncementOut)
async def manual_announcement(
    payload: ManualAnnouncementRequest,
    session: SessionDep,
    user: UserDep,
) -> AnnouncementOut:
    """Queue or immediately broadcast a custom spoken announcement."""
    voice_id = payload.voice_id
    if not voice_id:
        stmt = select(AIDJSettings).where(AIDJSettings.id == 1)
        res = await session.execute(stmt)
        s = res.scalar_one_or_none()
        voice_id = s.voice_id if s else "hi_IN-priyamvada-medium"

    try:
        ann = await dj_voice_service.set_manual_announcement(payload.text, voice_id=voice_id)
        radio_svc = RadioService(session)
        if payload.should_play_now:
            await radio_svc.trigger_announcement_now(ann, actor=user.email)
        else:
            await radio_svc.log(
                "voice",
                f"Manual announcement queued: '{payload.text[:40]}'",
                user.email,
                {"announcement_id": ann.id, "voice_id": voice_id},
            )
        return ann
    except Exception as exc:
        logger.exception("Manual announcement error: %s", exc)
        raise HTTPException(status_code=500, detail=f"Manual announcement failed: {exc}") from exc


@router.get("/stream/{announcement_id}")
@router.head("/stream/{announcement_id}")
async def stream_announcement(announcement_id: str) -> FileResponse:
    """Stream generated WAV announcement audio for playback."""
    file_path = tts_service.get_announcement_file(announcement_id)
    if not file_path:
        raise HTTPException(status_code=404, detail="Announcement audio file not found")
    return FileResponse(file_path, media_type="audio/wav", filename=f"{announcement_id}.wav")
