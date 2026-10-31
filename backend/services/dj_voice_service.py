"""AI DJ Voice Announcement Manager and Spoken Break Generator."""

from __future__ import annotations

import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo
import logging
from typing import Any, Optional

from schemas.radio import AnnouncementOut
from services.tts_service import tts_service

logger = logging.getLogger(__name__)


class DJVoiceService:
    """Manages AI DJ spoken introductions, outros, time checks, and advance synthesis."""

    def __init__(self) -> None:
        self._pending_announcement: AnnouncementOut | None = None
        self._songs_since_last_announcement: int = 0
        self._lock = asyncio.Lock()

    def get_time_greeting(self, language: str = "hi", tz_name: str = "Asia/Kolkata") -> str:
        """Generate a time-of-day greeting in the station timezone."""
        try:
            tz = ZoneInfo(tz_name)
        except Exception:
            tz = ZoneInfo("Asia/Kolkata")

        hour = datetime.now(tz).hour
        if language == "hi":
            if 4 <= hour < 12:
                return "शुभ प्रभात!"
            elif 12 <= hour < 17:
                return "नमस्ते, शुभ दोपहर!"
            elif 17 <= hour < 22:
                return "शुभ संध्या!"
            else:
                return "रेडियोपायलट नाइट शो में आपका स्वागत है!"
        else:
            if 4 <= hour < 12:
                return "Good morning!"
            elif 12 <= hour < 17:
                return "Good afternoon!"
            elif 17 <= hour < 22:
                return "Good evening!"
            else:
                return "Welcome to late night vibes on RadioPilot AI!"

    def compose_intro_script(
        self,
        song_title: str,
        artist: str,
        language: str = "hi",
        include_greeting: bool = True,
    ) -> str:
        """Compose a natural, radio-ready intro announcement."""
        greeting = self.get_time_greeting(language) if include_greeting else ""

        if language == "hi":
            templates = [
                f"{greeting} रेडियोपायलट एआई पर अब सुनिए {artist} का बेहतरीन गाना, {song_title}!",
                f"{greeting} संगीत का सफर आगे बढ़ाते हुए, पेश है {song_title}, जिसे गाया है {artist} ने। आनंद लीजिए!",
                f"{greeting} आप सुन रहे हैं रेडियोपायलट एआई। अगला खूबसूरत नगमा है {artist} का {song_title}!",
            ]
        else:
            templates = [
                f"{greeting} You're tuned into RadioPilot AI. Up next, here is {song_title} by {artist}!",
                f"{greeting} This is RadioPilot AI, keeping the rhythm going with {song_title} by {artist}. Turn up the volume!",
                f"{greeting} Broadcasting live on RadioPilot AI. Next track on deck is {song_title} by {artist}. Enjoy!",
            ]

        # Deterministic rotation based on length
        idx = (len(song_title) + len(artist)) % len(templates)
        return templates[idx].strip()

    def compose_outro_script(
        self,
        song_title: str,
        artist: str,
        language: str = "hi",
    ) -> str:
        """Compose a natural outro announcement for a finished track."""
        if language == "hi":
            return f"यह था {artist} का शानदार गाना {song_title}। रेडियोपायलट एआई के साथ बने रहिए!"
        return f"That was {song_title} by {artist} right here on RadioPilot AI. Stay tuned!"

    async def prepare_next_announcement(
        self,
        next_song_title: str,
        next_song_artist: str,
        settings: Any,
        previous_song_title: str | None = None,
        previous_song_artist: str | None = None,
    ) -> AnnouncementOut | None:
        """Synthesize next announcement in advance while current song is playing."""
        if not getattr(settings, "enabled", True):
            return None

        language = getattr(settings, "language", "hi")
        voice_id = getattr(settings, "voice_id", "hi_IN-priyamvada-medium")
        intro_enabled = getattr(settings, "intro_enabled", True)
        outro_enabled = getattr(settings, "outro_enabled", False)
        greeting_enabled = getattr(settings, "greeting_enabled", True)

        script_parts = []
        announcement_type = "intro"

        # Outro if enabled and previous song exists
        if outro_enabled and previous_song_title and previous_song_artist:
            outro_text = self.compose_outro_script(previous_song_title, previous_song_artist, language)
            script_parts.append(outro_text)
            announcement_type = "outro_intro"

        # Intro for next song
        if intro_enabled and next_song_title:
            intro_text = self.compose_intro_script(
                next_song_title,
                next_song_artist,
                language=language,
                include_greeting=greeting_enabled,
            )
            script_parts.append(intro_text)

        if not script_parts:
            return None

        full_script = " ".join(script_parts)

        try:
            audio = await tts_service.synthesize(full_script, voice_id=voice_id)
            announcement = AnnouncementOut(
                id=audio.id,
                text=audio.text,
                voice_id=audio.voice_id,
                duration_seconds=audio.duration_seconds,
                stream_url=f"/tts/stream/{audio.id}",
                announcement_type=announcement_type,
            )
            async with self._lock:
                self._pending_announcement = announcement
            logger.info("AI DJ announcement prepared in advance: '%s' (%s seconds)", full_script[:40], audio.duration_seconds)
            return announcement
        except Exception as exc:
            logger.exception("Failed to synthesize advance AI DJ announcement: %s", exc)
            return None

    async def get_and_consume_announcement(self, settings: Any) -> AnnouncementOut | None:
        """Retrieve and clear pending announcement if due based on announcement frequency."""
        if not getattr(settings, "enabled", True):
            async with self._lock:
                self._pending_announcement = None
            return None

        frequency = max(1, getattr(settings, "frequency", 1))

        async with self._lock:
            self._songs_since_last_announcement += 1
            if self._songs_since_last_announcement >= frequency:
                ann = self._pending_announcement
                self._pending_announcement = None
                if ann is not None:
                    self._songs_since_last_announcement = 0
                return ann
            return None

    async def set_manual_announcement(self, text: str, voice_id: str = "hi_IN-priyamvada-medium") -> AnnouncementOut:
        """Immediately synthesize and queue a manual announcement."""
        audio = await tts_service.synthesize(text, voice_id=voice_id)
        ann = AnnouncementOut(
            id=audio.id,
            text=audio.text,
            voice_id=audio.voice_id,
            duration_seconds=audio.duration_seconds,
            stream_url=f"/tts/stream/{audio.id}",
            announcement_type="manual",
        )
        async with self._lock:
            self._pending_announcement = ann
            self._songs_since_last_announcement = 999  # Force play on next transition
        return ann

    def clear_pending(self) -> None:
        """Clear any pending announcement."""
        self._pending_announcement = None


dj_voice_service = DJVoiceService()
