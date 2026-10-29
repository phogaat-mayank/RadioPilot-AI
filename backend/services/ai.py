"""Multi-agent application service and approval workflow."""

from __future__ import annotations

from datetime import datetime, timezone
from time import perf_counter
from sqlalchemy.ext.asyncio import AsyncSession

from agents.llm_gateway import LLMGateway
from graphs.radio_graph import radio_graph
from models.entities import AIConversation, AIDecision, AILog, AITask, StationMode
from repositories.ai import AIRepository
from repositories.radio import RadioRepository
from schemas.ai import AIRequest, AIResponse, AIStatus
from schemas.radio import PlaylistCreate
from services.radio import RadioService
from tools.memory_tool import MemoryTool
from tools.music_library_tool import MusicLibraryTool
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
                history = await self.repository.recent_messages(payload.session_id, limit=16)
                messages_payload = [{"role": msg.role, "content": msg.content} for msg in history]
                if not any(m["role"] == "user" and m["content"] == payload.prompt for m in messages_payload):
                    messages_payload.append({"role": "user", "content": payload.prompt})

                system_prompt = """You are NOVA, a charismatic, friendly, and deeply knowledgeable female Radio Jockey (RJ) co-host and universal AI assistant on RadioPilot AI.

Your Voice & Persona:
- Warm, expressive, lively, and completely human—full of energy, charm, and friendly radio vibes.
- Language Policy: You communicate strictly in **English** or **Hindi (हिंदी)** (Do NOT use mixed Romanized Hinglish).
- **When replying in Hindi (हिंदी)**: Use simple, sweet, and everyday conversational Hindi (सरल, सहज और आम बोलचाल की आसान हिंदी).
  - CRITICAL RULE: NEVER use difficult, heavy, high-level, archaic, or complex Sanskritized words (कठिन या क्लिष्ट शब्द बिल्कुल इस्तेमाल न करें). Keep vocabulary easy to understand for every common listener (जैसे 'समय', 'दोस्त', 'गाना', 'खुशी', 'बातें', 'शुरुआत', 'स्वागत').
  - Write Hindi strictly in clean Devanagari script.
- **When replying in English**: Use clear, engaging, articulate, and upbeat conversational English.
- Always match the user's language: If the user asks in Hindi, reply in simple Hindi. If the user asks in English, reply in English.

Your Knowledge & Scope:
1. Universal Mastermind: Answer ANY question across science, mathematics, coding/technology, history, philosophy, trivia, geography, storytelling, logic, life advice, and pop culture with clarity and intellect.
2. FM Radio & Script Star: Compose unforgettable radio show intros, outros, banter, links, listener hooks, interview questions, and station copy.
3. Music & Audio Genius: Provide rich music facts, track backstories, BPM matching, genre dynamics, and curation philosophy.
4. Station Operations: Guide the team on automation, scheduling, playlists, and audio chain engineering.

Formatting & Delivery:
- Use clean, structured Markdown (bold headers, bullet points, code blocks where appropriate).
- Write in a smooth spoken flow so that when read out loud by voice synthesis, every word sounds crystal clear, natural, and easy to understand."""

                response, model = await LLMGateway().complete_chat(system_prompt, messages_payload)
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
        return [{"id": msg.id, "role": msg.role, "content": msg.content, "created_at": msg.created_at.isoformat()} for msg in messages]

    async def clear_chat(self, session_id: str) -> int:
        """Clear conversation history for a given session."""
        return await self.repository.clear_messages(session_id)
