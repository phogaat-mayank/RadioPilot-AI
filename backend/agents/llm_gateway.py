"""LiteLLM and Groq gateway with multi-model fallback and multi-turn chat."""

from __future__ import annotations

import logging
from typing import Any
import httpx
from core.config import settings

logger = logging.getLogger(__name__)

# Preferred order of high-capacity models available on Groq
GROQ_FALLBACK_MODELS = [
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
    "qwen/qwen3.8-27b",
    "groq/compound",
]


class LLMGateway:
    """Centralize model-provider access, multi-turn history, and multi-model fallback."""

    async def complete(self, system_prompt: str, user_prompt: str) -> tuple[str, str]:
        """Return model output for a single user turn."""
        return await self.complete_chat(system_prompt, [{"role": "user", "content": user_prompt}])

    async def complete_chat(self, system_prompt: str, messages: list[dict[str, str]]) -> tuple[str, str]:
        """Return model output given conversation history, falling back gracefully."""
        if not settings.litellm_model or not settings.litellm_api_key:
            return self._offline_response(messages), "deterministic-offline"

        if settings.litellm_model.startswith("groq/") or settings.litellm_api_key.startswith("gsk_"):
            return await self._complete_groq_chat(system_prompt, messages)

        try:
            from litellm import acompletion
            formatted_messages = [{"role": "system", "content": system_prompt}, *messages]
            result = await acompletion(
                model=settings.litellm_model,
                api_key=settings.litellm_api_key,
                messages=formatted_messages,
                max_tokens=2048,
                temperature=0.7,
            )
            content = str(result.choices[0].message.content)
            return content, settings.litellm_model
        except Exception:
            logger.exception("LiteLLM request failed; trying Groq fallback")
            return await self._complete_groq_chat(system_prompt, messages)

    async def _complete_groq_chat(self, system_prompt: str, messages: list[dict[str, str]]) -> tuple[str, str]:
        """Attempt completion against Groq API with automatic model cascading."""
        api_key = settings.litellm_api_key
        if not api_key:
            return self._offline_response(messages), "deterministic-offline"

        raw_model = settings.litellm_model.removeprefix("groq/") if settings.litellm_model else "openai/gpt-oss-120b"
        
        # Build candidate models list starting with the configured model
        candidate_models = [raw_model] + [m for m in GROQ_FALLBACK_MODELS if m != raw_model]
        formatted_messages = [{"role": "system", "content": system_prompt}, *messages]

        async with httpx.AsyncClient(timeout=45.0) as client:
            for model_name in candidate_models:
                try:
                    response = await client.post(
                        "https://api.groq.com/openai/v1/chat/completions",
                        headers={
                            "Authorization": f"Bearer {api_key}",
                            "Content-Type": "application/json",
                        },
                        json={
                            "model": model_name,
                            "messages": formatted_messages,
                            "temperature": 0.7,
                            "max_tokens": 2048,
                        },
                    )
                    if response.status_code == 200:
                        payload: dict[str, Any] = response.json()
                        choices = payload.get("choices", [])
                        if choices and "message" in choices[0]:
                            content = choices[0]["message"].get("content") or ""
                            if content.strip():
                                return str(content), f"groq/{model_name}"
                    logger.warning("Groq model %s returned status %s: %s", model_name, response.status_code, response.text[:200])
                except Exception as ex:
                    logger.warning("Groq call failed for model %s: %s", model_name, ex)

        logger.error("All Groq model attempts failed; using fallback response")
        return self._offline_response(messages), "deterministic-fallback"

    def _offline_response(self, messages: list[dict[str, str]]) -> str:
        """Provide a helpful fallback answer when no LLM connection is available."""
        latest = messages[-1]["content"].lower() if messages else ""
        if "playlist" in latest:
            return "I can generate automated playlists organized by mood, tempo, and artist separation! Click the 'Generate playlist' button or specify your mood and duration."
        if "script" in latest or "intro" in latest:
            return "Here's a quick presenter link idea: 'Welcome back to RadioPilot! You are tuned into the freshest sound in town. Keep the energy high as we dive into our next track!'"
        if "news" in latest:
            return "Hourly news bulletins can be generated automatically from verified sources. Click 'Hourly news' to prepare a broadcast-ready bulletin."
        if "schedule" in latest:
            return "You can schedule upcoming music shows, commercial breaks, and news bulletins directly in the Schedules & Automation workspace."
        return "I am RJ AI, your radio co-host and universal assistant. I can answer any questions about general knowledge, science, music, show ideas, coding, or station operations."

