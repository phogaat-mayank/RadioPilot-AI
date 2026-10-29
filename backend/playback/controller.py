"""Thread-safe playback controller; the only audio-command authority."""

from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
import logging
import socket
from pathlib import Path
from typing import Protocol

from models.entities import Song

logger = logging.getLogger(__name__)


@dataclass
class SongSnapshot:
    """Session-decoupled song representation that prevents DetachedInstanceError."""
    id: int
    title: str
    artist: str
    album: str | None
    genre: str | None
    duration_seconds: float
    file_path: str

    @classmethod
    def from_song(cls, song: object | None) -> SongSnapshot | None:
        """Create a detached snapshot from an ORM entity or dict."""
        if song is None:
            return None
        if isinstance(song, cls):
            return song
        return cls(
            id=int(getattr(song, "id")),
            title=str(getattr(song, "title", "Unknown Title")),
            artist=str(getattr(song, "artist", "Unknown Artist")),
            album=getattr(song, "album", None),
            genre=getattr(song, "genre", None),
            duration_seconds=float(getattr(song, "duration_seconds", 0.0) or 0.0),
            file_path=str(getattr(song, "file_path", "")),
        )



class AudioEngine(Protocol):
    """Minimal audio-engine contract for VLC and future Liquidsoap adapters."""

    def play(self, path: str) -> None: ...
    def pause(self) -> None: ...
    def stop(self) -> None: ...
    def set_volume(self, volume: int) -> None: ...


class NullAudioEngine:
    """Safe development engine that tracks commands but emits no audio."""

    def play(self, path: str) -> None:
        """Accept a playback request without producing output."""
        logger.info("Null audio engine play", extra={"path": path})

    def pause(self) -> None:
        """Accept a pause request."""

    def stop(self) -> None:
        """Accept a stop request."""

    def set_volume(self, volume: int) -> None:
        """Accept a volume request."""


class VlcAudioEngine:
    """VLC adapter for real audio output, isolated from station policy."""

    def __init__(self, output: str = "") -> None:
        """Create one VLC media player, optionally targeting a VLC output module."""
        try:
            import vlc
        except ImportError as error:
            raise RuntimeError("python-vlc is unavailable; install VLC and python-vlc") from error
        options = [f"--aout={output}"] if output else []
        self._vlc = vlc.Instance(*options)
        self._player = self._vlc.media_player_new()

    def play(self, path: str) -> None:
        """Load and play a local media path."""
        media = self._vlc.media_new_path(path)
        self._player.set_media(media)
        self._player.play()

    def pause(self) -> None:
        """Toggle VLC pause state."""
        self._player.pause()

    def stop(self) -> None:
        """Stop VLC output."""
        self._player.stop()

    def set_volume(self, volume: int) -> None:
        """Set VLC output volume."""
        self._player.audio_set_volume(volume)


class LiquidsoapAudioEngine:
    """Queue-only Liquidsoap adapter that never exposes engine control to AI."""

    def __init__(self, host: str, port: int, media_prefix: str) -> None:
        """Configure the private Liquidsoap command endpoint and media mount."""
        self._host, self._port, self._media_prefix = host, port, Path(media_prefix)

    def play(self, path: str) -> None:
        """Push a shared-media request to Liquidsoap's dedicated queue."""
        mapped_path = self._media_prefix / Path(path).name
        self._command(f"queue.push {mapped_path}")

    def pause(self) -> None:
        """Pause is intentionally not mapped: broadcast outputs stay continuous."""
        logger.warning("Liquidsoap pause requested; preserving continuous broadcast output")

    def stop(self) -> None:
        """Skip the queued request without tearing down the encoder connection."""
        self._command("queue.skip")

    def set_volume(self, volume: int) -> None:
        """Keep volume state in RadioPilot; production gain belongs in Liquidsoap DSP."""
        logger.info("Liquidsoap gain update recorded", extra={"volume": volume})

    def _command(self, command: str) -> None:
        """Send one bounded command to the internal, unauthenticated control socket."""
        try:
            with socket.create_connection((self._host, self._port), timeout=2) as connection:
                connection.sendall(f"{command}\nexit\n".encode("utf-8"))
                reply = connection.recv(4096).decode("utf-8", errors="replace")
                if "ERROR" in reply.upper():
                    raise RuntimeError(reply.strip())
        except OSError as error:
            raise RuntimeError("Liquidsoap output service is unavailable") from error


class PlaybackController:
    """Serialize all playback operations and maintain broadcast state."""

    def __init__(self, engine: AudioEngine | None = None) -> None:
        """Create a controller backed by a safely swappable audio engine."""
        self._engine = engine or NullAudioEngine()
        self._queue: deque[SongSnapshot] = deque()
        self._history: deque[SongSnapshot] = deque(maxlen=100)
        self._current: SongSnapshot | None = None
        self._status = "stopped"
        self._position_seconds = 0.0
        self._started_at: datetime | None = None
        self._volume = 75
        self._playback_revision = 0
        self._lock = asyncio.Lock()

    async def queue(self, song: Song | SongSnapshot) -> None:
        """Append an asset to the playback queue."""
        snapshot = SongSnapshot.from_song(song)
        if snapshot:
            async with self._lock:
                self._queue.append(snapshot)

    async def queue_many(self, songs: list[Song | SongSnapshot]) -> None:
        """Append a validated sequence of assets."""
        snapshots = [s for s in (SongSnapshot.from_song(song) for song in songs) if s]
        async with self._lock:
            self._queue.extend(snapshots)

    async def clear_queue(self) -> int:
        """Clear all pending items from the playback queue."""
        async with self._lock:
            count = len(self._queue)
            self._queue.clear()
            return count

    async def interrupt_with_playlist(self, songs: list[Song | SongSnapshot]) -> None:
        """Start a priority playlist and retain the interrupted queue for resumption."""
        if not songs:
            raise ValueError("Cannot interrupt playback with an empty playlist")
        snapshots = [s for s in (SongSnapshot.from_song(song) for song in songs) if s]
        if not snapshots:
            raise ValueError("No valid songs found in playlist")
        async with self._lock:
            resume_queue = deque(self._queue)
            if self._current is not None:
                resume_queue.appendleft(self._current)
            target, remaining = snapshots[0], snapshots[1:]
            self._queue = deque(remaining)
            self._queue.extend(resume_queue)
            self._engine.play(target.file_path)
            self._current, self._status = target, "playing"
            self._position_seconds, self._started_at = 0.0, datetime.now(timezone.utc)
            self._playback_revision += 1

    async def play(self, song: Song | SongSnapshot | None = None) -> None:
        """Start a supplied asset or the next queued asset."""
        async with self._lock:
            target = SongSnapshot.from_song(song) if song is not None else (self._queue.popleft() if self._queue else None)
            if target is None:
                raise ValueError("Cannot play: queue is empty")
            if self._current and self._current.id != target.id:
                self._history.append(self._current)
            self._engine.play(target.file_path)
            self._current, self._status = target, "playing"
            self._position_seconds, self._started_at = 0.0, datetime.now(timezone.utc)
            self._playback_revision += 1

    async def pause(self) -> None:
        """Pause the current asset."""
        async with self._lock:
            if self._status != "playing":
                raise ValueError("Playback is not active")
            self._position_seconds = self._current_position_unlocked()
            self._engine.pause()
            self._status = "paused"

    async def resume(self) -> None:
        """Resume a paused asset."""
        async with self._lock:
            if self._status != "paused":
                raise ValueError("Playback is not paused")
            self._engine.pause()
            self._started_at = datetime.now(timezone.utc)
            self._status = "playing"

    async def stop(self) -> None:
        """Stop playback while retaining the queue."""
        async with self._lock:
            self._engine.stop()
            self._position_seconds, self._status, self._started_at = 0.0, "stopped", None

    async def skip(self) -> None:
        """End the current item and begin the next queued item."""
        async with self._lock:
            self._skip_unlocked()

    async def skip_if_revision(self, playback_revision: int) -> bool:
        """Advance only once for the browser event belonging to the current track."""
        async with self._lock:
            if playback_revision != self._playback_revision or self._status != "playing":
                return False
            self._skip_unlocked()
            return True

    async def previous(self) -> None:
        """Replay the last completed asset."""
        async with self._lock:
            if not self._history:
                raise ValueError("Playback history is empty")
            target = self._history.pop()
            if self._current:
                self._queue.appendleft(self._current)
            self._engine.play(target.file_path)
            self._current, self._status = target, "playing"
            self._position_seconds, self._started_at = 0.0, datetime.now(timezone.utc)
            self._playback_revision += 1

    async def set_volume(self, volume: int) -> None:
        """Set output volume after range validation by the caller."""
        async with self._lock:
            self._engine.set_volume(volume)
            self._volume = volume

    async def state(self) -> dict:
        """Return a snapshot suitable for serialization."""
        async with self._lock:
            return {
                "status": self._status,
                "volume": self._volume,
                "current_song": self._current,
                "current_position_seconds": round(self._current_position_unlocked(), 1),
                "playback_revision": self._playback_revision,
                "queue": list(self._queue),
                "updated_at": datetime.now(timezone.utc),
            }

    def _current_position_unlocked(self) -> float:
        """Calculate elapsed position without waiting on the audio backend."""
        if self._status == "playing" and self._started_at:
            return self._position_seconds + (datetime.now(timezone.utc) - self._started_at).total_seconds()
        return self._position_seconds

    def _skip_unlocked(self) -> None:
        if self._current:
            self._history.append(self._current)
        if not self._queue:
            self._engine.stop()
            self._current, self._status = None, "stopped"
            return
        target = self._queue.popleft()
        self._engine.play(target.file_path)
        self._current, self._status = target, "playing"
        self._position_seconds, self._started_at = 0.0, datetime.now(timezone.utc)
        self._playback_revision += 1


def create_audio_engine() -> AudioEngine:
    """Select a configured execution adapter without exposing it to agents."""
    from core.config import settings
    if settings.audio_engine.lower() == "vlc":
        return VlcAudioEngine(settings.vlc_output)
    if settings.audio_engine.lower() == "liquidsoap":
        return LiquidsoapAudioEngine(settings.liquidsoap_host, settings.liquidsoap_port, settings.liquidsoap_media_prefix)
    return NullAudioEngine()


playback_controller = PlaybackController(create_audio_engine())
