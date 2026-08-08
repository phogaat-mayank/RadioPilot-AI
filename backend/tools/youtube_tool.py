"""YouTube discovery tool for user-directed browser playback."""

from urllib.parse import urlencode
import httpx
from core.config import settings


class YouTubeTool:
    """Resolve a requested song to an official YouTube watch URL when configured."""

    async def play_url(self, query: str) -> tuple[str, bool]:
        """Return a first-video autoplay URL or a safe YouTube search fallback."""
        fallback = f"https://www.youtube.com/results?{urlencode({'search_query': query})}"
        if not settings.youtube_api_key or settings.youtube_api_key.startswith("your-"):
            return fallback, False
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get("https://www.googleapis.com/youtube/v3/search", params={"part": "snippet", "q": query, "type": "video", "maxResults": 1, "videoEmbeddable": "true", "safeSearch": "moderate", "key": settings.youtube_api_key})
                response.raise_for_status()
            items = response.json().get("items", [])
            video_id = items[0].get("id", {}).get("videoId") if items else None
            # Explicit playback parameters give YouTube the strongest permitted
            # autoplay hint when navigation originates from the dashboard.
            return (f"https://www.youtube.com/watch?v={video_id}&autoplay=1&mute=0&playsinline=1&rel=0", True) if video_id else (fallback, False)
        except httpx.HTTPError:
            return fallback, False
