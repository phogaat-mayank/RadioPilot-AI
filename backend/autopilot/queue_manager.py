"""Queue policy utilities that never touch the playback controller."""

from __future__ import annotations

from collections.abc import Iterable
from random import SystemRandom

from autopilot.autopilot_state import ActionType, AutopilotAction, MediaRef, StationState


class QueueManager:
    """Build queue-refill decisions while preventing avoidable duplicate rotation."""

    def __init__(self, minimum_depth: int = 8, maximum_depth: int = 20, fallback_playlist_ids: tuple[int, ...] = ()) -> None:
        if minimum_depth < 1 or maximum_depth < minimum_depth:
            raise ValueError("Queue depths must be positive and maximum_depth must be at least minimum_depth")
        self._minimum_depth = minimum_depth
        self._maximum_depth = maximum_depth
        self._fallback_playlist_ids = fallback_playlist_ids
        self._played_in_cycle: set[int] = set()

    def needs_refill(self, state: StationState) -> bool:
        """Return whether queue depth has fallen below the desired buffer."""
        return len(state.queue) < self._minimum_depth

    def refill_action(self, state: StationState, candidates: Iterable[MediaRef]) -> AutopilotAction:
        """Return a LOAD_QUEUE action with unique, available media candidates."""
        existing_ids = {song.id for song in state.queue}
        if state.current_song:
            existing_ids.add(state.current_song.id)
        catalog = [song for song in candidates if song.available]
        eligible = [song for song in catalog if song.id not in existing_ids and song.id not in self._played_in_cycle]
        if not eligible:
            self._played_in_cycle.clear()
            eligible = [song for song in catalog if song.id not in existing_ids]
        SystemRandom().shuffle(eligible)
        target_depth = self._maximum_depth if not state.queue else self._minimum_depth
        required = max(0, target_depth - len(state.queue))
        selected = eligible[:required]
        self._played_in_cycle.update(song.id for song in selected)
        if selected:
            return AutopilotAction(ActionType.LOAD_QUEUE, "Refill queue from eligible media", {"song_ids": [song.id for song in selected]}, priority=40)
        if self._fallback_playlist_ids:
            return AutopilotAction(ActionType.PLAY_PLAYLIST, "No unique queue candidates; use fallback playlist", {"playlist_id": self._fallback_playlist_ids[0], "fallback": True}, priority=45)
        return AutopilotAction(ActionType.NO_ACTION, "No eligible media exists to refill queue", priority=1000)

    def replacement_action(self, state: StationState, candidates: Iterable[MediaRef]) -> AutopilotAction:
        """Choose a replacement after a bad or missing current media asset."""
        action = self.refill_action(state.evolve(queue=()), candidates)
        if action.action_type is ActionType.LOAD_QUEUE:
            return AutopilotAction(ActionType.RECOVER_PLAYBACK, "Replacement media is available", {"replacement_song_ids": action.payload["song_ids"]}, priority=5)
        return action
