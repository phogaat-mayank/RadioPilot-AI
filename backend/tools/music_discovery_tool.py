"""Robust online music metadata discovery via multiple providers (iTunes, Deezer, MusicBrainz)."""

import asyncio
import logging
from time import monotonic
import httpx

logger = logging.getLogger(__name__)


class MusicDiscoveryTool:
    """Discover recording metadata across resilient public providers without downloading audio."""

    _lock = asyncio.Lock()
    _last_request = 0.0

    async def search(self, query: str, limit: int = 10) -> list[dict[str, str | int | None]]:
        """Search online metadata across resilient providers with automatic fallbacks."""
        clean_query = query.strip()
        if not clean_query:
            return []

        capped_limit = min(max(limit, 1), 25)

        # 1. Primary: iTunes Search API (fast, high availability, excellent global and Indian catalog)
        try:
            itunes_results = await self._search_itunes(clean_query, capped_limit)
            if itunes_results:
                return itunes_results
        except Exception as exc:
            logger.warning("iTunes music search failed for %r: %s", clean_query, exc)

        # 2. Secondary: Deezer Public API
        try:
            deezer_results = await self._search_deezer(clean_query, capped_limit)
            if deezer_results:
                return deezer_results
        except Exception as exc:
            logger.warning("Deezer music search failed for %r: %s", clean_query, exc)

        # 3. Tertiary: MusicBrainz (rate-limited, open community database)
        try:
            mb_results = await self._search_musicbrainz(clean_query, capped_limit)
            if mb_results:
                return mb_results
        except Exception as exc:
            logger.warning("MusicBrainz music search failed for %r: %s", clean_query, exc)

        return []

    async def _search_itunes(self, query: str, limit: int) -> list[dict[str, str | int | None]]:
        """Search Apple iTunes Search API."""
        async with httpx.AsyncClient(timeout=8.0) as client:
            response = await client.get(
                "https://itunes.apple.com/search",
                params={"media": "music", "entity": "song", "term": query, "limit": limit},
            )
            response.raise_for_status()
            data = response.json()

        results: list[dict[str, str | int | None]] = []
        for item in data.get("results", []):
            title = item.get("trackName") or item.get("collectionName")
            if not title:
                continue
            track_id = str(item.get("trackId") or f"itunes_{len(results) + 1}")
            artist = item.get("artistName") or "Unknown Artist"
            duration = round((item.get("trackTimeMillis") or 0) / 1000)
            release_date = (item.get("releaseDate") or "")[:10] or None

            results.append({
                "id": track_id,
                "title": title,
                "artist": artist,
                "duration_seconds": duration,
                "release_date": release_date,
            })
        return results

    async def _search_deezer(self, query: str, limit: int) -> list[dict[str, str | int | None]]:
        """Search Deezer API."""
        async with httpx.AsyncClient(timeout=8.0) as client:
            response = await client.get(
                "https://api.deezer.com/search",
                params={"q": query, "limit": limit},
            )
            response.raise_for_status()
            data = response.json()

        results: list[dict[str, str | int | None]] = []
        for item in data.get("data", []):
            title = item.get("title")
            if not title:
                continue
            track_id = str(item.get("id") or f"deezer_{len(results) + 1}")
            artist = (item.get("artist") or {}).get("name") or "Unknown Artist"
            duration = int(item.get("duration") or 0)

            results.append({
                "id": track_id,
                "title": title,
                "artist": artist,
                "duration_seconds": duration,
                "release_date": None,
            })
        return results

    async def _search_musicbrainz(self, query: str, limit: int) -> list[dict[str, str | int | None]]:
        """Search MusicBrainz while respecting its 1 req/sec rate limit."""
        async with self._lock:
            delay = 1.0 - (monotonic() - self._last_request)
            if delay > 0:
                await asyncio.sleep(delay)

            headers = {
                "User-Agent": "RadioPilotAI/1.0 (https://github.com/phogaat-mayank/RadioPilot-AI; support@radiopilot.ai)"
            }
            async with httpx.AsyncClient(timeout=10.0, headers=headers) as client:
                response = await client.get(
                    "https://musicbrainz.org/ws/2/recording",
                    params={"query": query, "fmt": "json", "limit": limit},
                )
                response.raise_for_status()
                data = response.json()
            self._last_request = monotonic()

        results: list[dict[str, str | int | None]] = []
        for item in data.get("recordings", []):
            title = item.get("title")
            if not title:
                continue
            track_id = str(item.get("id") or f"mb_{len(results) + 1}")
            artist = ", ".join(credit.get("name", "") for credit in item.get("artist-credit", [])) or "Unknown Artist"
            duration = round((item.get("length") or 0) / 1000)
            release_date = item.get("first-release-date")

            results.append({
                "id": track_id,
                "title": title,
                "artist": artist,
                "duration_seconds": duration,
                "release_date": release_date,
            })
        return results
