"""Verified-headline radio bulletin composition."""

from __future__ import annotations

import re
from datetime import datetime
import httpx
from xml.etree import ElementTree


class NewsTool:
    """Format supplied verified news into a concise broadcast bulletin."""

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
            return (
                f"HOURLY NEWS — {timestamp}\n\n"
                "No verified headlines were supplied. Paste 1–5 trusted headlines into the RJ AI box, "
                "then press Hourly news to create a broadcast-ready bulletin."
            )
        lines = [f"HOURLY NEWS — {timestamp}", "", "INTRO: Here are the latest verified headlines at this hour."]
        lines.extend(f"{index}. {headline.rstrip('.')} ." for index, headline in enumerate(clean, start=1))
        lines.extend(["", "OUTRO: That’s the latest update. We’ll bring you more verified news in the next bulletin.", "Read steadily; do not add facts that are not in the supplied headlines."])
        return "\n".join(lines)

    @staticmethod
    async def fetch_rss_headlines(limit: int = 4) -> list[str]:
        """Fetch concise headlines from public RSS sources with automatic fallback."""
        rss_feeds = [
            "https://feeds.bbci.co.uk/news/world/rss.xml",
            "https://rss.nytimes.com/services/xml/rss/nyt/World.xml",
            "https://feeds.npr.org/1001/rss.xml",
        ]
        headers = {"User-Agent": "RadioPilotAI/1.0 (news bulletin reader)"}
        for feed_url in rss_feeds:
            try:
                async with httpx.AsyncClient(timeout=6.0, follow_redirects=True) as client:
                    response = await client.get(feed_url, headers=headers)
                    response.raise_for_status()
                root = ElementTree.fromstring(response.content)
                items = [title.text.strip() for title in root.findall(".//item/title") if title.text and title.text.strip()]
                if items:
                    return items[:limit]
            except Exception:
                continue
        return []

    @classmethod
    async def automatic_bulletin(cls, duration_seconds: int = 60, mix: list[str] | None = None) -> dict:
        """Prepare a short factual bulletin with rotating news/weather-style sections."""
        categories = mix or ["headlines", "weather", "station"]
        headlines = await cls.fetch_rss_headlines(limit=3)
        bullets = headlines[:3]
        if "weather" in categories:
            bullets.append("Weather update: check local conditions and travel advisories before heading out.")
        if "station" in categories:
            bullets.append("Stay tuned for music, traffic, and the next verified update from RadioPilot AI.")
        bullets = bullets[: max(2, min(5, duration_seconds // 12))]
        if not headlines:
            bullets = ["No verified external headlines are available right now.", *bullets]
        return {"prepared_at": datetime.now().isoformat(), "duration_seconds": max(30, min(120, duration_seconds)), "mix": categories, "bullets": bullets, "script": "\n".join(f"• {bullet}" for bullet in bullets)}
