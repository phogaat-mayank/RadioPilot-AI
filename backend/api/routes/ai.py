"""Authenticated multi-agent AI routes."""

from fastapi import APIRouter, HTTPException, Query
from api.deps import SessionDep, UserDep
from schemas.ai import AIDecisionUpdate, AIRequest, AIResponse, AIStatus
from services.ai import AIService
from services.radio import RadioService
from tools.music_discovery_tool import MusicDiscoveryTool
from tools.youtube_tool import YouTubeTool

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
async def music_search(_: UserDep, q: str = Query(min_length=2, max_length=120), limit: int = Query(default=10, ge=1, le=25)) -> list[dict]:
    """Search online music metadata; results never include unlicensed audio files."""
    try:
        return await MusicDiscoveryTool().search(q, limit)
    except Exception as error:
        raise HTTPException(status_code=502, detail="Online music search is temporarily unavailable") from error


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


@router.get("/history")
async def history(session: SessionDep, _: UserDep) -> list[dict]:
    """Return recent multi-agent activity."""
    return await AIService(session).history()


@router.put("/decisions/{decision_id}", status_code=204)
async def decide(decision_id: int, payload: AIDecisionUpdate, session: SessionDep, user: UserDep) -> None:
    """Approve or reject a proposed AI action."""
    if not await AIService(session).decide(decision_id, payload.approved, user.email):
        raise HTTPException(status_code=404, detail="AI decision not found")
