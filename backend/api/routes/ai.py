"""Authenticated multi-agent AI routes."""

from datetime import datetime, timedelta, timezone
import logging
import re
from fastapi import APIRouter, HTTPException, Query
from api.deps import SessionDep, UserDep
from schemas.ai import AIDecisionUpdate, AIRequest, AIResponse, AIStatus
from services.ai import AIService
from services.radio import RadioService
from repositories.radio import RadioRepository
from tools.music_discovery_tool import MusicDiscoveryTool
from tools.youtube_tool import YouTubeTool

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ai", tags=["RJ AI"])


async def _execute(action: str, payload: AIRequest, session: SessionDep, user: UserDep) -> AIResponse:
    """Route a specialist action through the shared AI service."""
    try:
        return await AIService(session).execute(action, payload, user.email)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.post("/chat", response_model=AIResponse)
async def chat(payload: AIRequest, session: SessionDep, user: UserDep) -> AIResponse:
    """Talk to RJ AI."""
    return await _execute("chat", payload, session, user)


@router.get("/chat/history")
async def get_chat_history(session: SessionDep, _: UserDep, session_id: str = Query(default="dashboard"), limit: int = Query(default=30, ge=1, le=100)) -> list[dict]:
    """Retrieve recent multi-turn conversation messages."""
    return await AIService(session).chat_history(session_id=session_id, limit=limit)


@router.delete("/chat/history")
async def clear_chat_history(session: SessionDep, _: UserDep, session_id: str = Query(default="dashboard")) -> dict[str, int]:
    """Clear chat messages for the specified session."""
    deleted_count = await AIService(session).clear_chat(session_id=session_id)
    return {"deleted": deleted_count}


@router.post("/schedule", response_model=AIResponse)
async def schedule(payload: AIRequest, session: SessionDep, user: UserDep) -> AIResponse:
    """Request a schedule recommendation."""
    return await _execute("schedule", payload, session, user)


@router.post("/playlist", response_model=AIResponse)
async def playlist(payload: AIRequest, session: SessionDep, user: UserDep) -> AIResponse:
    """Request a curated playlist proposal."""
    return await _execute("playlist", payload, session, user)


@router.post("/script", response_model=AIResponse)
async def script(payload: AIRequest, session: SessionDep, user: UserDep) -> AIResponse:
    """Generate a presenter script."""
    return await _execute("script", payload, session, user)


@router.post("/news", response_model=AIResponse)
async def news(payload: AIRequest, session: SessionDep, user: UserDep) -> AIResponse:
    """Format a verified-headline news bulletin."""
    return await _execute("news", payload, session, user)


@router.post("/ads", response_model=AIResponse)
async def ads(payload: AIRequest, session: SessionDep, user: UserDep) -> AIResponse:
    """Request advertisement placement advice."""
    return await _execute("ads", payload, session, user)


@router.post("/analyze", response_model=AIResponse)
async def analyze(payload: AIRequest, session: SessionDep, user: UserDep) -> AIResponse:
    """Analyze provided aggregate station metrics."""
    return await _execute("analyze", payload, session, user)


@router.get("/music/search")
async def music_search(
    session: SessionDep,
    _: UserDep,
    q: str = Query(min_length=2, max_length=120),
    limit: int = Query(default=10, ge=1, le=25),
) -> list[dict]:
    """Search online music metadata; results never include unlicensed audio files."""
    try:
        results = await MusicDiscoveryTool().search(q, limit)
        if results:
            return results
    except Exception as error:
        logger.warning("Online music search provider error for query %r: %s", q, error)

    # Fallback to local library matching songs if online returned no results
    try:
        local_songs = await RadioRepository(session).list_songs()
        q_lower = q.lower()
        matches = [
            {
                "id": f"local_{song.id}",
                "title": song.title,
                "artist": song.artist,
                "duration_seconds": song.duration_seconds,
                "release_date": None,
            }
            for song in local_songs
            if q_lower in song.title.lower() or q_lower in song.artist.lower()
        ]
        if matches:
            return matches[:limit]
    except Exception as local_err:
        logger.warning("Local library search fallback error: %s", local_err)

    return []


@router.get("/youtube/play-url")
async def youtube_play_url(_: UserDep, q: str = Query(min_length=2, max_length=200)) -> dict[str, object]:
    """Resolve a spoken song request to a browser-safe YouTube destination."""
    try:
        url, autoplay = await YouTubeTool().play_url(q)
        return {"url": url, "autoplay": autoplay}
    except Exception as error:
        raise HTTPException(status_code=502, detail="YouTube search is temporarily unavailable") from error


@router.post("/voice/command", response_model=AIResponse)
async def voice_command(payload: AIRequest, session: SessionDep, user: UserDep) -> AIResponse:
    """Execute safe spoken station controls or route natural language to RJ AI."""
    command = payload.prompt.lower().strip()
    if any(phrase in command for phrase in ["start autopilot", "autopilot chalu", "autopilot start"]):
        await AIService(session).set_autopilot(True, user.email)
        return AIResponse(task_id=0, agent="voice_controller", status="completed", response="Autopilot started.")
    if any(phrase in command for phrase in ["stop autopilot", "manual mode", "manual chalu"]):
        await AIService(session).set_autopilot(False, user.email)
        return AIResponse(task_id=0, agent="voice_controller", status="completed", response="Manual mode started.")
    if command in {"play", "play music", "gaana chalao", "song chalao"}:
        try:
            await RadioService(session).play(None, user.email)
            return AIResponse(task_id=0, agent="voice_controller", status="completed", response="Playing the next queued song.")
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
    if any(phrase in command for phrase in ["skip", "next song", "next track", "agla gaana"]):
        await RadioService(session).command("skip", user.email)
        return AIResponse(task_id=0, agent="voice_controller", status="completed", response="Skipped to the next song.")
    if any(phrase in command for phrase in ["pause", "stop music", "music rok", "gaana rok"]):
        await RadioService(session).command("pause", user.email)
        return AIResponse(task_id=0, agent="voice_controller", status="completed", response="Playback paused.")
    if any(phrase in command for phrase in ["resume", "continue music", "music chalao"]):
        await RadioService(session).command("resume", user.email)
        return AIResponse(task_id=0, agent="voice_controller", status="completed", response="Playback resumed.")
    volume = re.search(r"(?:volume|awaz|sound)\s*(?:to|ko|at)?\s*(\d{1,3})", command)
    if volume:
        value = max(0, min(100, int(volume.group(1))))
        await RadioService(session).set_volume(value, user.email)
        return AIResponse(task_id=0, agent="voice_controller", status="completed", response=f"Volume set to {value} percent.")
    if any(phrase in command for phrase in ["generate playlist", "playlist banao", "playlist bana"]):
        return await _execute("playlist", payload.model_copy(update={"mood": payload.mood or "balanced", "duration_minutes": payload.duration_minutes or 60}), session, user)
    if any(phrase in command for phrase in ["generate script", "script banao", "rj script"]):
        return await _execute("script", payload, session, user)
    if any(phrase in command for phrase in ["hourly news", "news bulletin", "news banao"]):
        return await _execute("news", payload, session, user)
    return await _execute("chat", payload, session, user)


@router.post("/autopilot/start", response_model=AIStatus)
async def start_autopilot(session: SessionDep, user: UserDep) -> AIStatus:
    """Enable AI station ownership without interrupting playback."""
    return await AIService(session).set_autopilot(True, user.email)


@router.post("/autopilot/stop", response_model=AIStatus)
async def stop_autopilot(session: SessionDep, user: UserDep) -> AIStatus:
    """Stop AI decisions and return ownership to manual control."""
    return await AIService(session).set_autopilot(False, user.email)


@router.post("/manual/start", response_model=AIStatus)
async def start_manual(session: SessionDep, user: UserDep) -> AIStatus:
    """Explicitly enable manual RJ control."""
    return await AIService(session).set_autopilot(False, user.email)


@router.get("/status", response_model=AIStatus)
async def status(session: SessionDep, _: UserDep) -> AIStatus:
    """Return AI workload and station ownership status."""
    return await AIService(session).status()


@router.get("/news/on-air")
async def on_air_news(session: SessionDep, _: UserDep) -> dict[str, object] | None:
    """Return the currently triggered prepared bulletin for the dashboard voice reader."""
    now = datetime.now(timezone.utc)
    schedules = await RadioRepository(session).list_schedules()
    for schedule in reversed(schedules):
        if not schedule.enabled or schedule.event_type != "news":
            continue
        metadata = dict(schedule.metadata_json or {})
        broadcast_at = metadata.get("broadcast_at")
        bullets = metadata.get("bullets")
        if not isinstance(broadcast_at, str) or not isinstance(bullets, list):
            continue
        try:
            broadcast_time = datetime.fromisoformat(broadcast_at.replace("Z", "+00:00"))
            if broadcast_time.tzinfo is None:
                broadcast_time = broadcast_time.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        duration = max(30, min(120, int(metadata.get("duration_seconds", 60))))
        if now <= broadcast_time + timedelta(seconds=duration + 15):
            return {
                "schedule_id": schedule.id,
                "broadcast_at": broadcast_time.isoformat(),
                "duration_seconds": duration,
                "bullets": [str(bullet) for bullet in bullets if str(bullet).strip()],
            }
    return None


@router.get("/history")
async def history(session: SessionDep, _: UserDep) -> list[dict]:
    """Return recent multi-agent activity."""
    return await AIService(session).history()


@router.put("/decisions/{decision_id}", status_code=204)
async def decide(decision_id: int, payload: AIDecisionUpdate, session: SessionDep, user: UserDep) -> None:
    """Approve or reject a proposed AI action."""
    if not await AIService(session).decide(decision_id, payload.approved, user.email):
        raise HTTPException(status_code=404, detail="AI decision not found")
