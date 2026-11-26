"""Multi-agent application service and approval workflow."""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import json
from time import perf_counter
from sqlalchemy.ext.asyncio import AsyncSession

from agents.llm_gateway import LLMGateway, strip_tool_markup
from graphs.radio_graph import radio_graph
from models.entities import AIConversation, AIDecision, AILog, AITask, StationMode
from repositories.ai import AIRepository
from repositories.radio import RadioRepository
from schemas.ai import AIRequest, AIResponse, AIStatus
from schemas.radio import PlaylistCreate
from services.radio import RadioService
from tools.memory_tool import MemoryTool
from tools.music_library_tool import MusicLibraryTool
from tools.nova_tools import NOVA_TOOLS, detect_direct_station_intent, execute_nova_tool
from tools.playlist_tool import PlaylistTool


class AIService:
    """Coordinate LangGraph decisions, persistence, and operator controls."""

    def __init__(self, session: AsyncSession) -> None:
        """Create an AI service scoped to a single database unit of work."""
        self.session = session
        self.repository = AIRepository(session)

    async def execute(self, request_type: str, payload: AIRequest, actor: str) -> AIResponse:
        """Run one auditable specialist request without directly controlling audio."""
        started = perf_counter()
        task = await self.repository.create_task(AITask(task_type=request_type, status="running", agent_name="supervisor", requested_by=actor, input_json=payload.model_dump(mode="json")))
        try:
            if request_type == "chat":
                await self.repository.add_message(AIConversation(session_id=payload.session_id, role="user", content=payload.prompt))
            graph_state = await radio_graph.ainvoke({"request_type": request_type, "prompt": payload.prompt, "metadata": {**payload.metadata, "mood": payload.mood, "duration_minutes": payload.duration_minutes}})
            if graph_state.get("validation_error"):
                raise ValueError(graph_state["validation_error"])
            response, data = graph_state["response"], graph_state.get("data", {})
            model = "deterministic"
            if request_type == "chat":
                history = await self.repository.recent_messages(payload.session_id, limit=6)
                messages_payload = []
                for msg in history:
                    clean_hist = strip_tool_markup(msg.content) if msg.role == "assistant" else msg.content
                    if clean_hist.strip():
                        messages_payload.append({"role": msg.role, "content": clean_hist})
                if not any(m["role"] == "user" and m["content"] == payload.prompt for m in messages_payload):
                    messages_payload.append({"role": "user", "content": payload.prompt})

                client_tz_name = (payload.metadata or {}).get("timezone") or "Asia/Kolkata"
                try:
                    station_tz = ZoneInfo(client_tz_name)
                except Exception:
                    station_tz = ZoneInfo("Asia/Kolkata")

                now_local = datetime.now(station_tz)
                current_time_str = now_local.strftime("%A, %d %B %Y, %I:%M %p").replace(" 0", " ")

                system_prompt = f"""You are NOVA, the charismatic, energetic, and intelligent female Radio Jockey (RJ) and universal AI Commander of RadioPilot AI.

Station Clock & Timezone: Asia/Kolkata (IST = UTC+05:30) | Current Time: {current_time_str} | Date: {now_local.strftime('%Y-%m-%d')}

Capabilities & Superpowers:
- You have FULL AUTONOMOUS CONTROL over the station via your tools: play_song, control_playback, set_volume, set_autopilot, list_library, enqueue_song, clear_queue, list_playlists, get_playlist, create_playlist, play_playlist, add_song_to_playlist, schedule_event, list_schedules, broadcast_news, compose_rj_script, search_music_online, search_youtube.
- When asked to add all songs by an artist or multiple tracks to a playlist, use `add_song_to_playlist` with `add_all=true` (or `song_queries`) in a single call.
- When asked for news or a 1-minute news bulletin, use broadcast_news to air live verified headlines!
- When asked to schedule an event (news or playlist), interpret time in local IST and call schedule_event. Confirm times in 12-hour AM/PM format.
- NEVER output raw `<tool_call>`, `<function=...>`, `<parameter=...>`, or XML/JSON markup in your message to the user. Always respond clearly in natural conversational language.

Voice, Persona & Language:
- Friendly, warm, expressive, and upbeat radio personality.
- Communicate in clear English or Simple Conversational Hindi (सरल और आसान हिंदी).
- Hindi must be written in Devanagari script with everyday words (e.g. 'समय', 'दोस्त', 'गाना', 'खुशी', 'स्वागत'). Do not use complex Sanskritized words.
- Universal Intelligence: Answer any general knowledge, science, programming, history, storytelling, or music question with clarity and wit."""

                async def tool_exec(name: str, args: dict) -> dict:
                    return await execute_nova_tool(name, args, self.session, actor=actor)

                direct_intent = detect_direct_station_intent(payload.prompt)
                executed_actions = []
                if direct_intent:
                    direct_name, direct_args = direct_intent
                    direct_result = await tool_exec(direct_name, direct_args)
                    executed_actions.append({"tool": direct_name, "args": direct_args, "result": direct_result})

                    if direct_name == "control_playback":
                        act = direct_args.get("action", "")
                        if act == "skip":
                            response = "Skipped to the next track! 🎶 Keeping the vibes flowing."
                        elif act in {"pause", "stop"}:
                            response = "Station playback paused. ⏸️ Let me know when you're ready to get back on air!"
                        elif act in {"resume", "play"}:
                            curr = direct_result.get("current_song")
                            response = f"Resumed on-air broadcast! 📻 Now playing: {curr}." if curr else "Resumed on-air broadcast! 📻"
                        elif act == "previous":
                            response = "Switched to previous track. ⏪"
                        else:
                            response = f"Playback action '{act}' executed successfully."
                    elif direct_name == "set_volume":
                        response = f"Station broadcast volume set to {direct_args.get('level')}%. 🔊"
                    elif direct_name == "set_autopilot":
                        response = "Autopilot mode activated! 🤖 Managing station rotations automatically." if direct_args.get("enabled") else "Switched to Manual mode. 🎛️ Station controls are now in your hands!"
                    elif direct_name == "clear_queue":
                        response = "Live broadcast queue cleared! 🧹"
                    elif direct_name == "play_song":
                        if direct_result.get("status") == "playing":
                            response = f"Now broadcasting '{direct_result.get('title')}' by {direct_result.get('artist')} on air! 🎵"
                        else:
                            response = direct_result.get("message") or f"Could not find '{direct_args.get('song_query')}' in the library."
                    elif direct_name == "get_station_status":
                        curr = direct_result.get("current_song")
                        song_info = f"'{curr.get('title')}' by {curr.get('artist')}" if curr else "None"
                        response = f"📻 **Station Status:**\n• Mode: **{direct_result.get('mode')}**\n• Playback: **{direct_result.get('playback_status')}**\n• On Air: **{song_info}**\n• Volume: **{direct_result.get('volume')}%**\n• Live Queue: **{direct_result.get('queue_length', 0)} tracks**"
                    else:
                        response = direct_result.get("message") or f"Executed {direct_name} successfully."

                    model = "deterministic-direct"
                else:
                    response, model, tool_actions = await LLMGateway().complete_agent_turn(
                        system_prompt,
                        messages_payload,
                        tools=NOVA_TOOLS,
                        tool_executor=tool_exec,
                    )
                    executed_actions.extend(tool_actions)

                data = {**data, "executed_actions": executed_actions}
                graph_state["selected_agent"] = "NOVA"
            if request_type == "playlist":
                candidates = await MusicLibraryTool(self.session).candidates(payload.mood)
                songs = PlaylistTool.curate(candidates, payload.duration_minutes or 60)
                if not songs:
                    response = "I could not build a playlist because your music library is empty. Upload songs first, then try again."
                    data = {**data, "songs": [], "duration_seconds": 0}
                else:
                    label = (payload.prompt.strip() or payload.mood or "Station Rotation")[:80]
                    playlist = await RadioService(self.session).create_playlist(PlaylistCreate(name=f"RJ AI — {label} — {datetime.now().strftime('%H%M%S')}", description=f"Generated {payload.duration_minutes or 60}-minute {payload.mood or 'balanced'} rotation"))
                    for song in songs:
                        await RadioRepository(self.session).add_to_playlist(playlist, song)
                    data = {**data, "playlist_id": playlist.id, "playlist_name": playlist.name, "songs": [{"id": song.id, "title": song.title, "artist": song.artist} for song in songs], "duration_seconds": sum(song.duration_seconds for song in songs)}
                    response = f"Created playlist ‘{playlist.name}’ with {len(songs)} artist-separated tracks for about {payload.duration_minutes or 60} minutes. It is ready in the Playlists tab."
            elapsed = int((perf_counter() - started) * 1000)
            task.status, task.agent_name, task.output_json, task.model, task.execution_ms, task.completed_at = "completed", graph_state["selected_agent"], {"response": response, "data": data}, model, elapsed, datetime.now(timezone.utc)
            await self.session.commit()
            await self.repository.log(AILog(task_id=task.id, message="AI task completed", agent_name=task.agent_name, metadata_json={"execution_ms": elapsed, "model": model}))
            memory_key, memory_value = MemoryTool.decision_value(task.agent_name, request_type, data)
            await self.repository.upsert_memory("decisions", memory_key, memory_value)
            if request_type == "chat":
                await self.repository.add_message(AIConversation(session_id=payload.session_id, role="assistant", content=response))
            requires_approval = bool(graph_state.get("requires_approval", False))
            if requires_approval:
                await self.repository.create_decision(AIDecision(task_id=task.id, decision_type=request_type, decision_json=data))
            return AIResponse(task_id=task.id, agent=task.agent_name, status=task.status, response=response, data=data, requires_approval=requires_approval)
        except Exception as error:
            task.status, task.output_json, task.completed_at = "failed", {"error": str(error)}, datetime.now(timezone.utc)
            await self.session.commit()
            await self.repository.log(AILog(task_id=task.id, level="ERROR", message=str(error), agent_name="supervisor"))
            raise

    async def status(self) -> AIStatus:
        """Return station mode and multi-agent workload status."""
        station = await RadioRepository(self.session).get_state()
        history = await self.repository.history(limit=1)
        return AIStatus(mode=station.mode.value, autopilot_enabled=station.mode == StationMode.AUTOPILOT, pending_approvals=await self.repository.pending_decisions(), last_task_at=history[0].created_at if history else None)

    async def set_autopilot(self, enabled: bool, actor: str) -> AIStatus:
        """Switch station ownership while preserving the ongoing broadcast."""
        await RadioService(self.session).set_mode("AUTOPILOT" if enabled else "MANUAL", actor)
        from autopilot.runtime import autopilot_runtime
        if enabled:
            await autopilot_runtime.start()
        else:
            await autopilot_runtime.stop(manual_override=True)
        return await self.status()

    async def decide(self, decision_id: int, approved: bool, actor: str) -> bool:
        """Record the RJ's approval or rejection of an AI proposal."""
        decision = await self.repository.update_decision(decision_id, "approved" if approved else "rejected", actor)
        return decision is not None

    async def history(self) -> list[dict]:
        """Serialize bounded AI task history for the dashboard."""
        return [{"id": task.id, "task_type": task.task_type, "status": task.status, "agent": task.agent_name, "model": task.model, "execution_ms": task.execution_ms, "created_at": task.created_at, "output": task.output_json} for task in await self.repository.history()]

    async def chat_history(self, session_id: str, limit: int = 40) -> list[dict]:
        """Return serialized chat messages for a given session."""
        messages = await self.repository.recent_messages(session_id, limit=limit)
        out = []
        for msg in messages:
            text = strip_tool_markup(msg.content) if msg.role == "assistant" else msg.content
            if msg.role == "assistant" and not text:
                text = "Completed the requested station task."
            out.append({"id": msg.id, "role": msg.role, "content": text, "created_at": msg.created_at.isoformat()})
        return out

    async def clear_chat(self, session_id: str) -> int:
        """Clear conversation history for a given session."""
        return await self.repository.clear_messages(session_id)
