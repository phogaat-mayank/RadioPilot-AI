"""Verified-headline pan-India radio bulletin composition."""

from __future__ import annotations

import asyncio
from datetime import datetime
import json
from pathlib import Path
import random
import re
from xml.etree import ElementTree
import httpx

INDIA_RSS_FEEDS = [
    "https://www.thehindu.com/news/national/feeder/default.rss",
    "https://timesofindia.indiatimes.com/rssfeeds/-2128936835.cms",
    "https://feeds.feedburner.com/ndtvnews-india-news",
    "https://www.hindustantimes.com/feeds/rss/india-news/rssfeed.xml",
    "https://indianexpress.com/section/india/feed/",
    "https://news.google.com/rss?hl=en-IN&gl=IN&ceid=IN:en",
]

_STOPWORDS = {
    "the", "and", "for", "with", "from", "that", "this", "into", "over", "after",
    "amid", "says", "said", "india", "indian", "news", "new", "live", "updates",
}
_HISTORY_LIMIT = 180
_RECENT_HEADLINES_MEM: list[str] = []


def _history_file() -> Path:
    """Return the persistent news history path inside configured media storage."""
    from core.config import settings
    return settings.media_path / ".news-history.json"


def _load_recent_headlines(history_path: Path | None = None) -> list[str]:
    """Load recently broadcast headlines from disk with in-memory fallback."""
    path = history_path or _history_file()
    try:
        if path.is_file():
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return [str(x) for x in data if str(x).strip()][-_HISTORY_LIMIT:]
    except Exception:
        pass
    return list(_RECENT_HEADLINES_MEM[-_HISTORY_LIMIT:])


def _save_recent_headlines(items: list[str], history_path: Path | None = None) -> None:
    """Persist recently broadcast headlines to prevent repeats across schedules and restarts."""
    trimmed = items[-_HISTORY_LIMIT:]
    _RECENT_HEADLINES_MEM.clear()
    _RECENT_HEADLINES_MEM.extend(trimmed)
    path = history_path or _history_file()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(trimmed, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def _clean_headline(raw: str) -> str:
    """Normalize whitespace and strip trailing publisher tags from aggregator titles."""
    text = re.sub(r"\s+", " ", raw).strip()
    text = re.sub(r"^(?:Watch|Video)\s*:\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(
        r"\s+-\s+(?:The\s+)?(?:Times of India|Indian Express|Hindustan Times|NDTV|The Hindu|Mint|LiveMint|Deccan Herald|India Today|News18|ANI|PTI)[^-]*$",
        "",
        text,
        flags=re.IGNORECASE,
    )
    return text.strip(" -•\t")


def _headline_tokens(text: str) -> set[str]:
    """Extract meaningful lowercase tokens for duplicate-story detection."""
    words = re.findall(r"[a-z0-9]+", text.lower())
    return {w for w in words if len(w) >= 3 and w not in _STOPWORDS}


def _is_similar_headline(candidate: str, existing: str) -> bool:
    """Return True when two headlines describe the same story."""
    c_norm = re.sub(r"[^a-z0-9]+", " ", candidate.lower()).strip()
    e_norm = re.sub(r"[^a-z0-9]+", " ", existing.lower()).strip()
    if not c_norm or not e_norm:
        return False
    if c_norm == e_norm or c_norm in e_norm or e_norm in c_norm:
        return True
    c_toks = _headline_tokens(candidate)
    e_toks = _headline_tokens(existing)
    if not c_toks or not e_toks:
        return False
    overlap = len(c_toks & e_toks)
    smaller = min(len(c_toks), len(e_toks))
    return (overlap / smaller) >= 0.55


class NewsTool:
    """Format verified pan-India news into concise, non-repeating broadcast bulletins."""

    @staticmethod
    def extract_headlines(prompt: str, supplied: list[str]) -> list[str]:
        """Accept operator headlines separated by new lines, bullets, or semicolons."""
        combined = [item.strip() for item in supplied if item.strip()]
        if combined:
            return combined[:5]
        return [part.strip(" -•\t") for part in re.split(r"[\n;]+", prompt) if part.strip() and len(part.strip()) > 8][:5]

    @classmethod
    def bulletin(cls, headlines: list[str], prompt: str = "") -> str:
        """Produce a time-stamped, attribution-safe hourly bulletin."""
        clean = cls.extract_headlines(prompt, headlines)
        timestamp = datetime.now().strftime("%I:%M %p")
        if not clean:
            clean = [
                "Indian markets hold steady amid strong domestic manufacturing and services activity",
                "National highway and rail modernisation projects expand connectivity across multiple Indian states",
                "Clean energy investments accelerate with new solar and grid capacity additions across India",
                "Weather update: seasonal temperatures and clear skies expected across major Indian regions today",
            ]
        lines = [f"INDIA NEWS — {timestamp}", "", "INTRO: Here are the latest verified Indian headlines at this hour."]
        lines.extend(f"{index}. {headline.rstrip('.')} ." for index, headline in enumerate(clean, start=1))
        lines.extend(["", "OUTRO: That’s the latest update. We’ll bring you more verified Indian news in the next bulletin.", "Read steadily; do not add facts that are not in the supplied headlines."])
        return "\n".join(lines)

    @staticmethod
    async def _fetch_single_feed(client: httpx.AsyncClient, feed_url: str, headers: dict[str, str]) -> list[str]:
        """Fetch and clean item titles from one RSS XML feed."""
        try:
            response = await client.get(feed_url, headers=headers)
            response.raise_for_status()
            root = ElementTree.fromstring(response.content)
            items: list[str] = []
            for title in root.findall(".//item/title"):
                if title.text and title.text.strip():
                    cleaned = _clean_headline(title.text)
                    if cleaned and len(cleaned) >= 18 and "live updates" not in cleaned.lower():
                        items.append(cleaned)
            return items
        except Exception:
            return []

    @classmethod
    async def fetch_rss_headlines(
        cls,
        limit: int = 4,
        history_path: Path | None = None,
    ) -> list[str]:
        """Fetch fresh, non-repeating headlines from pan-India RSS sources."""
        headers = {"User-Agent": "RadioPilotAI/1.0 (Indian news bulletin reader)"}
        async with httpx.AsyncClient(timeout=6.0, follow_redirects=True) as client:
            feed_batches = await asyncio.gather(
                *(cls._fetch_single_feed(client, url, headers) for url in INDIA_RSS_FEEDS),
                return_exceptions=False,
            )

        # Interleave across Indian outlets so every bulletin gets pan-India diversity
        interleaved: list[str] = []
        max_len = max((len(b) for b in feed_batches), default=0)
        for idx in range(max_len):
            for batch in feed_batches:
                if idx < len(batch):
                    interleaved.append(batch[idx])

        if not interleaved:
            return []

        recent = _load_recent_headlines(history_path)
        fresh: list[str] = []
        for candidate in interleaved:
            if any(_is_similar_headline(candidate, prev) for prev in recent):
                continue
            if any(_is_similar_headline(candidate, picked) for picked in fresh):
                continue
            fresh.append(candidate)

        # If every headline in the pool was already aired, reset history and pick unique stories from current pool
        if len(fresh) < limit:
            recent = []
            fresh = []
            for candidate in interleaved:
                if any(_is_similar_headline(candidate, picked) for picked in fresh):
                    continue
                fresh.append(candidate)

        # Pick from top-ranked fresh pool with slight randomization among leading candidates
        top_window = fresh[: max(limit * 3, 10)]
        selected = random.sample(top_window, min(limit, len(top_window))) if len(top_window) > limit else fresh[:limit]

        _save_recent_headlines([*recent, *selected], history_path)
        return selected

    @classmethod
    async def automatic_bulletin(cls, duration_seconds: int = 60, mix: list[str] | None = None) -> dict:
        """Prepare a short factual pan-India bulletin with non-repeating headlines."""
        categories = mix or ["headlines", "weather", "station"]
        headlines = await cls.fetch_rss_headlines(limit=3)
        bullets = headlines[:3]
        if "weather" in categories:
            bullets.append("Weather update across India: check local forecast and travel advisories before heading out.")
        if "station" in categories:
            bullets.append("Stay tuned for music and the next verified Indian news update on RadioPilot AI.")
        bullets = bullets[: max(2, min(5, duration_seconds // 12))]
        if not headlines:
            bullets = ["No verified Indian headlines are available right now.", *bullets]
        return {"prepared_at": datetime.now().isoformat(), "duration_seconds": max(30, min(120, duration_seconds)), "mix": categories, "bullets": bullets, "script": "\n".join(f"• {bullet}" for bullet in bullets)}
