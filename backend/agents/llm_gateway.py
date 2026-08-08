"""LiteLLM gateway with deterministic offline fallback."""

import logging
import httpx
from core.config import settings

logger = logging.getLogger(__name__)


class LLMGateway:
    """Centralize model-provider access and isolate provider failures."""

    async def complete(self, system_prompt: str, user_prompt: str) -> tuple[str, str]:
        """Return model output or deterministic fallback when no model is configured."""
        if not settings.litellm_model or not settings.litellm_api_key:
            return user_prompt, "deterministic"
        if settings.litellm_model.startswith("groq/"):
            return await self._complete_groq(system_prompt, user_prompt)
        try:
            from litellm import acompletion
            result = await acompletion(model=settings.litellm_model, api_key=settings.litellm_api_key, messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}])
            return str(result.choices[0].message.content), settings.litellm_model
        except Exception:
            logger.exception("LiteLLM request failed; using deterministic fallback")
            return user_prompt, "deterministic-fallback"

    async def _complete_groq(self, system_prompt: str, user_prompt: str) -> tuple[str, str]:
        """Use Groq's OpenAI-compatible API without importing a broken LiteLLM build."""
        model = settings.litellm_model.removeprefix("groq/")
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post("https://api.groq.com/openai/v1/chat/completions", headers={"Authorization": f"Bearer {settings.litellm_api_key}"}, json={"model": model, "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}], "temperature": 0.7, "max_tokens": 700})
                response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            return str(content), settings.litellm_model
        except (httpx.HTTPError, KeyError, IndexError):
            logger.exception("Groq request failed; using deterministic fallback")
            return user_prompt, "deterministic-fallback"
