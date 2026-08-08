"""Rate-limited online music metadata discovery via MusicBrainz."""

import asyncio
from time import monotonic
import httpx


class MusicDiscoveryTool:
    """Discover recording metadata without downloading or copying audio."""

    _lock = asyncio.Lock()
    _last_request = 0.0

    async def search(self, query: str, limit: int = 10) -> list[dict[str, str | int | None]]:
        """Search MusicBrainz while respecting its one-request-per-second policy."""
        async with self._lock:
            delay = 1.0 - (monotonic() - self._last_request)
            if delay > 0:
                await asyncio.sleep(delay)
            async with httpx.AsyncClient(timeout=10, headers={"User-Agent": "RadioPilotAI/1.0 (local music discovery)"}) as client:
                response = await client.get("https://musicbrainz.org/ws/2/recording", params={"query": query, "fmt": "json", "limit": min(max(limit, 1), 25)})
                response.raise_for_status()
            self._last_request = monotonic()
        return [{"id": item.get("id"), "title": item.get("title"), "artist": ", ".join(credit.get("name", "") for credit in item.get("artist-credit", [])), "duration_seconds": round((item.get("length") or 0) / 1000), "release_date": item.get("first-release-date")} for item in response.json().get("recordings", [])]
