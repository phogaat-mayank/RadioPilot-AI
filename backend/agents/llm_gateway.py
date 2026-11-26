"""LiteLLM and Groq gateway with multi-model fallback and multi-turn chat."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any, Callable, Coroutine
import httpx
from core.config import settings

logger = logging.getLogger(__name__)

# Preferred order of high-capacity models available on Groq
GROQ_FALLBACK_MODELS = [
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
    "qwen/qwen3.8-27b",
]

_TOOL_MARKUP_RE = re.compile(
    r"<(?:tool_call|function=[^>]*|parameter=[^>]*)>[\s\S]*?(?:</(?:tool_call|function|parameter)>|$)|</(?:tool_call|function|parameter)>",
    re.IGNORECASE,
)


def strip_tool_markup(content: str) -> str:
    """Remove leaked XML/pseudo-JSON tool call tags before returning text to callers."""
    if not content:
        return ""
    cleaned = _TOOL_MARKUP_RE.sub("", content)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _parse_param_value(raw_val: str) -> Any:
    """Coerce string parameter values inside XML tool call tags into native Python types."""
    val = raw_val.strip()
    if val.lower() == "true":
        return True
    if val.lower() == "false":
        return False
    if (val.startswith("[") and val.endswith("]")) or (val.startswith("{") and val.endswith("}")):
        try:
            return json.loads(val)
        except Exception:
            return val
    return val


def _extract_text_tool_calls(content: str) -> list[tuple[str, dict[str, Any]]]:
    """Extract XML or JSON `<tool_call>` blocks emitted in plain text by open-weight models."""
    if not content or ("<tool_call" not in content.lower() and "<function=" not in content.lower()):
        return []

    calls: list[tuple[str, dict[str, Any]]] = []
    # Format 1: <function=name><parameter=k>v</parameter>...</function>
    for func_name, body in re.findall(
        r"<function=([a-zA-Z0-9_]+)\s*>([\s\S]*?)(?:</function>|</tool_call>|$)",
        content,
        flags=re.IGNORECASE,
    ):
        args: dict[str, Any] = {}
        for key, raw_val in re.findall(
            r"<parameter=([a-zA-Z0-9_]+)\s*>([\s\S]*?)(?:</parameter>|(?=<parameter=)|$)",
            body,
            flags=re.IGNORECASE,
        ):
            args[key.strip()] = _parse_param_value(raw_val)
        calls.append((func_name.strip(), args))

    if calls:
        return calls

    # Format 2: <tool_call>{"name": "...", "arguments": {...}}</tool_call>
    for raw_json in re.findall(r"<tool_call>\s*(\{[\s\S]*?\})\s*(?:</tool_call>|$)", content, flags=re.IGNORECASE):
        try:
            obj = json.loads(raw_json)
            name = str(obj.get("name", "")).strip()
            raw_args = obj.get("arguments", {})
            args = json.loads(raw_args) if isinstance(raw_args, str) else (raw_args if isinstance(raw_args, dict) else {})
            if name:
                calls.append((name, args))
        except Exception:
            continue
    return calls


def _summarize_executed_actions(executed_actions: list[dict[str, Any]]) -> str:
    """Build a concise human-readable confirmation from executed station actions."""
    read_only_tools = {"list_library", "list_playlists", "get_playlist", "list_schedules", "get_station_status"}
    mutating_msgs: list[str] = []
    fallback_msgs: list[str] = []

    for act in executed_actions:
        tool_name = str(act.get("tool", ""))
        res = act.get("result", {})
        if not isinstance(res, dict):
            continue
        msg = str(res.get("message") or "").strip()
        if not msg:
            msg = f"Completed {tool_name}."
        if tool_name in read_only_tools:
            if msg not in fallback_msgs:
                fallback_msgs.append(msg)
        elif msg not in mutating_msgs:
            mutating_msgs.append(msg)

    chosen = mutating_msgs or fallback_msgs
    return "\n".join(chosen) if chosen else "Done!"


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
            content = strip_tool_markup(str(result.choices[0].message.content))
            return content, settings.litellm_model
        except Exception:
            logger.exception("LiteLLM request failed; trying Groq fallback")
            return await self._complete_groq_chat(system_prompt, messages)

    async def complete_agent_turn(
        self,
        system_prompt: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        tool_executor: Callable[[str, dict[str, Any]], Coroutine[Any, Any, dict[str, Any]]],
        max_turns: int = 6,
    ) -> tuple[str, str, list[dict[str, Any]]]:
        """Execute autonomous tool calling with multi-turn loop and model cascading."""
        api_key = settings.litellm_api_key
        if not api_key:
            return self._offline_response(messages), "deterministic-offline", []

        raw_model = settings.litellm_model.removeprefix("groq/") if settings.litellm_model else "openai/gpt-oss-120b"
        candidate_models = [raw_model] + [m for m in GROQ_FALLBACK_MODELS if m != raw_model]

        executed_actions: list[dict[str, Any]] = []
        current_messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}, *messages]

        async with httpx.AsyncClient(timeout=45.0) as client:
            for model_name in candidate_models:
                try:
                    turns = 0
                    while turns < max_turns:
                        turns += 1
                        payload: dict[str, Any] = {
                            "model": model_name,
                            "messages": current_messages,
                            "temperature": 0.7,
                            "max_tokens": 768,
                        }
                        # Keep tools enabled across turns so multi-step workflows complete;
                        # omit tools on the final turn to force a natural conversational closure.
                        if tools and turns < max_turns:
                            payload["tools"] = tools
                            payload["tool_choice"] = "auto"

                        response = await client.post(
                            "https://api.groq.com/openai/v1/chat/completions",
                            headers={
                                "Authorization": f"Bearer {api_key}",
                                "Content-Type": "application/json",
                            },
                            json=payload,
                        )
                        if response.status_code == 429:
                            logger.warning("Groq model %s hit 429 TPM limit: %s", model_name, response.text[:200])
                            await asyncio.sleep(1.0)
                            break
                        if response.status_code != 200:
                            logger.warning("Groq model %s error %s: %s", model_name, response.status_code, response.text[:200])
                            break

                        data = response.json()
                        choices = data.get("choices", [])
                        if not choices:
                            break
                        assistant_msg = choices[0].get("message", {})
                        tool_calls = assistant_msg.get("tool_calls")

                        if tool_calls:
                            current_messages.append(assistant_msg)
                            for tc in tool_calls:
                                call_id = tc.get("id", f"call_{turns}")
                                func_info = tc.get("function", {})
                                func_name = func_info.get("name", "")
                                raw_args = func_info.get("arguments", "{}")
                                try:
                                    func_args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                                except Exception:
                                    func_args = {}

                                logger.info("NOVA autonomous action: %s(%s)", func_name, func_args)
                                tool_result = await tool_executor(func_name, func_args)
                                executed_actions.append({"tool": func_name, "args": func_args, "result": tool_result})

                                current_messages.append({
                                    "role": "tool",
                                    "tool_call_id": call_id,
                                    "name": func_name,
                                    "content": json.dumps(tool_result, ensure_ascii=False),
                                })
                            continue

                        raw_content = str(assistant_msg.get("content") or "")
                        xml_calls = _extract_text_tool_calls(raw_content)
                        if xml_calls:
                            tool_outcomes: list[dict[str, Any]] = []
                            for func_name, func_args in xml_calls:
                                logger.info("NOVA recovered XML tool call: %s(%s)", func_name, func_args)
                                tool_result = await tool_executor(func_name, func_args)
                                executed_actions.append({"tool": func_name, "args": func_args, "result": tool_result})
                                tool_outcomes.append({"tool": func_name, "result": tool_result})

                            if turns < max_turns:
                                visible_prefix = strip_tool_markup(raw_content)
                                if visible_prefix:
                                    current_messages.append({"role": "assistant", "content": visible_prefix})
                                current_messages.append({
                                    "role": "system",
                                    "content": (
                                        f"Executed station actions: {json.dumps(tool_outcomes, ensure_ascii=False)}. "
                                        "If more actions remain, call tools using JSON function calling; otherwise reply clearly in natural language without any XML or <tool_call> tags."
                                    ),
                                })
                                continue

                        clean_content = strip_tool_markup(raw_content)
                        if clean_content:
                            return clean_content, f"groq/{model_name}", executed_actions
                        if executed_actions:
                            return _summarize_executed_actions(executed_actions), f"groq/{model_name}", executed_actions
                        break
                except Exception as ex:
                    logger.warning("Groq agent loop exception on %s: %s", model_name, ex)

        if executed_actions:
            return _summarize_executed_actions(executed_actions), "deterministic-agent", executed_actions

        return self._offline_response(messages), "deterministic-fallback", []

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
                            "max_tokens": 384,
                        },
                    )
                    if response.status_code == 200:
                        payload: dict[str, Any] = response.json()
                        choices = payload.get("choices", [])
                        if choices and "message" in choices[0]:
                            content = strip_tool_markup(choices[0]["message"].get("content") or "")
                            if content:
                                return content, f"groq/{model_name}"
                    elif response.status_code == 429:
                        logger.warning("Groq model %s hit 429 TPM limit: %s", model_name, response.text[:200])
                        await asyncio.sleep(1.0)
                        continue
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
            return "Live hourly news bulletins are generated from verified news feeds. Click 'Hourly news' or schedule a 1-minute bulletin on the station calendar!"
        if "schedule" in latest:
            return "You can schedule upcoming music shows, commercial breaks, and news bulletins directly in the Schedules & Automation workspace."
        return "I am NOVA (RJ AI), your live FM Radio Jockey co-host and universal assistant. I am right here and ready for your music requests, questions, or station controls!"

