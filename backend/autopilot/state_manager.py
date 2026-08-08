"""Safe in-memory and optional durable state storage for autopilot."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from pathlib import Path

from autopilot.autopilot_state import StationState

logger = logging.getLogger(__name__)


class StateManager:
    """Own an immutable station snapshot behind an asyncio lock."""

    def __init__(self, initial_state: StationState | None = None, persistence_path: Path | None = None) -> None:
        self._state = initial_state or StationState()
        self._path = persistence_path
        self._lock = asyncio.Lock()

    async def snapshot(self) -> StationState:
        """Read the latest state without exposing mutable internals."""
        async with self._lock:
            return self._state

    async def replace(self, state: StationState) -> StationState:
        """Atomically replace the state and persist it when configured."""
        async with self._lock:
            self._state = state
            await self._save_unlocked()
            return self._state

    async def update(self, mutate: Callable[[StationState], StationState]) -> StationState:
        """Apply one pure state transformation atomically."""
        async with self._lock:
            candidate = mutate(self._state)
            if not isinstance(candidate, StationState):
                raise TypeError("State mutation must return StationState")
            self._state = candidate
            await self._save_unlocked()
            return self._state

    async def save(self) -> None:
        """Persist an explicit recovery point."""
        async with self._lock:
            await self._save_unlocked()

    async def restore(self) -> StationState:
        """Restore a previous recovery point if it exists."""
        if self._path is None or not self._path.exists():
            return await self.snapshot()
        try:
            payload = await asyncio.to_thread(self._path.read_text, encoding="utf-8")
            state = StationState.from_dict(json.loads(payload))
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            logger.exception("Autopilot state restore failed", extra={"path": str(self._path)})
            return await self.snapshot()
        return await self.replace(state)

    async def _save_unlocked(self) -> None:
        if self._path is None:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        encoded = json.dumps(self._state.to_dict(), separators=(",", ":"), sort_keys=True)
        temporary = self._path.with_suffix(".tmp")
        await asyncio.to_thread(temporary.write_text, encoded, encoding="utf-8")
        await asyncio.to_thread(temporary.replace, self._path)
