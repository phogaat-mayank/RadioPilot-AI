"""Authenticated playback, mode, status, and real-time endpoints."""

from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect

from api.deps import SessionDep, UserDep
from database.session import SessionLocal
from schemas.radio import ModeChange, PlaybackState, QueueSong, TrackEnded, VolumeChange
from services.radio import RadioService
from websocket.manager import manager
from workflows.autopilot import autopilot_graph

router = APIRouter(prefix="/station", tags=["station control"])


@router.get("/status", response_model=PlaybackState)
async def status(session: SessionDep, _: UserDep) -> PlaybackState:
    """Return the current broadcast and control state."""
    return await RadioService(session).state()


@router.post("/queue", response_model=PlaybackState)
async def queue(payload: QueueSong, session: SessionDep, user: UserDep) -> PlaybackState:
    """Add a library asset to the live queue."""
    try:
        return await RadioService(session).enqueue_song(payload.song_id, user.email)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.delete("/queue", response_model=PlaybackState)
async def clear_queue(session: SessionDep, user: UserDep) -> PlaybackState:
    """Clear all assets currently in the live queue."""
    return await RadioService(session).clear_queue(user.email)


@router.post("/play", response_model=PlaybackState)
async def play(session: SessionDep, user: UserDep, song_id: int | None = Query(default=None)) -> PlaybackState:
    """Start one requested song or the next queued song."""
    try:
        return await RadioService(session).play(song_id, user.email)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/track-ended", response_model=PlaybackState)
async def track_ended(payload: TrackEnded, session: SessionDep, user: UserDep) -> PlaybackState:
    """Accept one browser completion event for the active playback revision."""
    return await RadioService(session).track_ended(payload.playback_revision, user.email)


@router.post("/{command}", response_model=PlaybackState)
async def playback_command(command: str, session: SessionDep, user: UserDep) -> PlaybackState:
    """Run a bounded pause, resume, stop, skip, or previous command."""
    try:
        return await RadioService(session).command(command, user.email)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.put("/volume", response_model=PlaybackState)
async def volume(payload: VolumeChange, session: SessionDep, user: UserDep) -> PlaybackState:
    """Set output volume."""
    return await RadioService(session).set_volume(payload.volume, user.email)


@router.put("/mode", response_model=PlaybackState)
async def mode(payload: ModeChange, session: SessionDep, user: UserDep) -> PlaybackState:
    """Switch manual/autopilot control ownership without stopping audio."""
    return await RadioService(session).set_mode(payload.mode, user.email)


@router.post("/autopilot/recommendation")
async def autopilot_recommendation(session: SessionDep, _: UserDep) -> dict:
    """Run decision-only LangGraph and return an auditable recommendation."""
    state = await RadioService(session).state()
    if state.mode != "AUTOPILOT":
        raise HTTPException(status_code=409, detail="Autopilot recommendations are frozen in manual mode")
    result = await autopilot_graph.ainvoke({"mode": state.mode, "queue": [song.id for song in state.queue]})
    await RadioService(session).log("agent", "Autopilot recommendation generated", details=result["recommendation"])
    return result["recommendation"]


@router.websocket("/ws/state")
async def state_socket(websocket: WebSocket) -> None:
    """Stream state snapshots to dashboards; browser auth remains API-token based."""
    await manager.connect(websocket)
    try:
        async with SessionLocal() as session:
            state = await RadioService(session).state()
            await websocket.send_json(state.model_dump(mode="json"))
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect(websocket)
