"""Broadcast-ready presenter script composition."""

from __future__ import annotations

from datetime import datetime


class ScriptTool:
    """Create practical, speakable links for radio presenters."""

    @staticmethod
    def compose(prompt: str, tone: str = "warm, energetic and natural") -> str:
        """Produce a complete presenter link with opener, audience hook, and close."""
        brief = prompt.strip().rstrip(".") or "a fresh radio segment"
        time_of_day = "morning" if 5 <= datetime.now().hour < 12 else "afternoon" if datetime.now().hour < 17 else "evening"
        return (
            f"RJ SCRIPT — {time_of_day.title()} Link\n\n"
            f"OPEN: \"You’re listening to RadioPilot AI. I’m your RJ, and this is {brief}.\"\n\n"
            f"LINK: \"Whether you’re on the road, at work, or relaxing at home, stay with us for great music and good company.\"\n\n"
            f"AUDIENCE HOOK: \"Send us your song requests and tell us what’s making your day better.\"\n\n"
            f"OUTRO: \"Coming up next, more of the songs you love. This is RadioPilot AI.\"\n\n"
            f"Delivery: {tone}. Keep each line conversational and pause naturally after the audience hook."
        )
