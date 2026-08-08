"""Playlist policy validation utilities."""

from models.entities import Song


class PlaylistTool:
    """Select songs without duplicates or adjacent artist repetition."""

    @staticmethod
    def curate(songs: list[Song], duration_minutes: int = 60) -> list[Song]:
        """Create a duration-bounded sequence respecting artist separation."""
        selected: list[Song] = []
        seen_ids: set[int] = set()
        last_artist = ""
        elapsed = 0.0
        for song in songs:
            if song.id in seen_ids or song.artist.casefold() == last_artist.casefold():
                continue
            if elapsed + song.duration_seconds > duration_minutes * 60 and selected:
                break
            selected.append(song)
            seen_ids.add(song.id)
            last_artist, elapsed = song.artist, elapsed + song.duration_seconds
        return selected
