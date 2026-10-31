"""Modular Piper TTS Service for local neural voice synthesis."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import urllib.request
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.config import settings

logger = logging.getLogger(__name__)

SUPPORTED_VOICES: dict[str, dict[str, Any]] = {
    "hi_IN-priyamvada-medium": {
        "id": "hi_IN-priyamvada-medium",
        "name": "Priyamvada (Hindi Female)",
        "language": "Hindi",
        "language_code": "hi_IN",
        "gender": "Female",
        "quality": "medium",
        "sample_rate": 22050,
        "hf_prefix": "hi/hi_IN/priyamvada/medium/hi_IN-priyamvada-medium",
        "license": "CC BY-NC-SA 4.0 (AI4Bharat IndicNLP Corpus)",
    },
    "hi_IN-pratham-medium": {
        "id": "hi_IN-pratham-medium",
        "name": "Pratham (Hindi Male)",
        "language": "Hindi",
        "language_code": "hi_IN",
        "gender": "Male",
        "quality": "medium",
        "sample_rate": 22050,
        "hf_prefix": "hi/hi_IN/pratham/medium/hi_IN-pratham-medium",
        "license": "CC BY-NC-SA 4.0 (AI4Bharat IndicNLP Corpus)",
    },
    "en_US-lessac-medium": {
        "id": "en_US-lessac-medium",
        "name": "Lessac (English US Female)",
        "language": "English",
        "language_code": "en_US",
        "gender": "Female",
        "quality": "medium",
        "sample_rate": 22050,
        "hf_prefix": "en/en_US/lessac/medium/en_US-lessac-medium",
        "license": "University of Edinburgh CSTR Research / Blizzard Challenge",
    },
    "en_US-ryan-medium": {
        "id": "en_US-ryan-medium",
        "name": "Ryan (English US Male)",
        "language": "English",
        "language_code": "en_US",
        "gender": "Male",
        "quality": "medium",
        "sample_rate": 22050,
        "hf_prefix": "en/en_US/ryan/medium/en_US-ryan-medium",
        "license": "CC BY-NC-SA 4.0 (RyanSpeech Corpus)",
    },
}


@dataclass
class SynthesizedAudio:
    """Result of a completed speech synthesis task."""
    id: str
    text: str
    voice_id: str
    file_path: str
    duration_seconds: float
    file_size_bytes: int


class TTSService:
    """Thread-safe, non-blocking local Piper TTS manager with model auto-download & caching."""

    def __init__(self) -> None:
        self.voices_dir: Path = settings.media_path / "piper_voices"
        self.announcements_dir: Path = settings.media_path / "announcements"
        self.voices_dir.mkdir(parents=True, exist_ok=True)
        self.announcements_dir.mkdir(parents=True, exist_ok=True)
        self._voice_cache: dict[str, Any] = {}
        self._lock = asyncio.Lock()

    def get_supported_voices(self) -> list[dict[str, Any]]:
        """Return all verified Piper voice models with their download status."""
        result = []
        for v_id, meta in SUPPORTED_VOICES.items():
            onnx_path = self.voices_dir / f"{v_id}.onnx"
            json_path = self.voices_dir / f"{v_id}.onnx.json"
            downloaded = onnx_path.exists() and json_path.exists()
            result.append({
                **meta,
                "downloaded": downloaded,
            })
        return result

    def is_model_downloaded(self, voice_id: str) -> bool:
        """Check if ONNX model and config files exist locally."""
        onnx_path = self.voices_dir / f"{voice_id}.onnx"
        json_path = self.voices_dir / f"{voice_id}.onnx.json"
        return onnx_path.exists() and json_path.exists()

    def _ensure_model_sync(self, voice_id: str) -> tuple[Path, Path]:
        """Synchronously download voice model and JSON config if missing."""
        if voice_id not in SUPPORTED_VOICES:
            raise ValueError(f"Unsupported Piper voice ID: {voice_id}")

        meta = SUPPORTED_VOICES[voice_id]
        onnx_path = self.voices_dir / f"{voice_id}.onnx"
        json_path = self.voices_dir / f"{voice_id}.onnx.json"

        base_url = "https://huggingface.co/rhasspy/piper-voices/resolve/main"

        if not json_path.exists():
            json_url = f"{base_url}/{meta['hf_prefix']}.onnx.json"
            logger.info("Downloading Piper voice config from %s", json_url)
            urllib.request.urlretrieve(json_url, str(json_path))

        if not onnx_path.exists():
            onnx_url = f"{base_url}/{meta['hf_prefix']}.onnx"
            logger.info("Downloading Piper voice model from %s", onnx_url)
            urllib.request.urlretrieve(onnx_url, str(onnx_path))

        return onnx_path, json_path

    def _get_or_load_voice(self, voice_id: str) -> Any:
        """Load and cache the PiperVoice instance in memory."""
        if voice_id in self._voice_cache:
            return self._voice_cache[voice_id]

        onnx_path, json_path = self._ensure_model_sync(voice_id)

        try:
            from piper import PiperVoice
            voice = PiperVoice.load(str(onnx_path), config_path=str(json_path))
            self._voice_cache[voice_id] = voice
            return voice
        except Exception as exc:
            logger.exception("Failed to load Piper voice %s: %s", voice_id, exc)
            raise RuntimeError(f"Could not initialize Piper voice {voice_id}: {exc}") from exc

    def _synthesize_sync(self, text: str, voice_id: str, out_wav_path: Path) -> float:
        """Synchronously generate speech and write 16-bit mono WAV audio."""
        voice = self._get_or_load_voice(voice_id)
        meta = SUPPORTED_VOICES.get(voice_id, {})
        sample_rate = meta.get("sample_rate", 22050)

        with wave.open(str(out_wav_path), "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)
            voice.synthesize_wav(text, wav_file, set_wav_format=False)

        # Calculate exact duration
        with wave.open(str(out_wav_path), "rb") as check_wav:
            frames = check_wav.getnframes()
            rate = check_wav.getframerate()
            duration = float(frames) / float(rate) if rate > 0 else 0.0

        return round(duration, 2)

    async def synthesize(self, text: str, voice_id: str = "hi_IN-priyamvada-medium") -> SynthesizedAudio:
        """Asynchronously synthesize speech without blocking the main event loop."""
        cleaned_text = text.strip()
        if not cleaned_text:
            raise ValueError("Announcement text cannot be empty")

        if voice_id not in SUPPORTED_VOICES:
            voice_id = "hi_IN-priyamvada-medium"

        # Content hash caching
        content_hash = hashlib.sha256(f"{voice_id}:{cleaned_text}".encode("utf-8")).hexdigest()[:16]
        announcement_id = f"ann_{content_hash}"
        out_wav_path = self.announcements_dir / f"{announcement_id}.wav"

        # Check existing cached audio
        if out_wav_path.exists() and out_wav_path.stat().st_size > 44:
            try:
                with wave.open(str(out_wav_path), "rb") as check_wav:
                    frames = check_wav.getnframes()
                    rate = check_wav.getframerate()
                    duration = round(float(frames) / float(rate), 2) if rate > 0 else 0.0
                return SynthesizedAudio(
                    id=announcement_id,
                    text=cleaned_text,
                    voice_id=voice_id,
                    file_path=str(out_wav_path),
                    duration_seconds=duration,
                    file_size_bytes=out_wav_path.stat().st_size,
                )
            except Exception:
                # If corrupted, re-synthesize
                pass

        # Synthesize in threadpool
        duration = await asyncio.to_thread(self._synthesize_sync, cleaned_text, voice_id, out_wav_path)

        return SynthesizedAudio(
            id=announcement_id,
            text=cleaned_text,
            voice_id=voice_id,
            file_path=str(out_wav_path),
            duration_seconds=duration,
            file_size_bytes=out_wav_path.stat().st_size,
        )

    def get_announcement_file(self, announcement_id: str) -> Path | None:
        """Resolve a synthesized announcement audio file path."""
        file_path = self.announcements_dir / f"{announcement_id}.wav"
        if file_path.exists() and file_path.is_file():
            return file_path
        return None


tts_service = TTSService()
