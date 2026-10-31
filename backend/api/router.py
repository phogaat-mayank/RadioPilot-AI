"""Versioned API route aggregation."""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from api.routes import ai, auth, library, playlists, schedules, station, tts
from database.session import SessionLocal
from services.radio import RadioService
from websocket.manager import manager

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(library.router)
api_router.include_router(playlists.router)
api_router.include_router(schedules.router)
api_router.include_router(station.router)
api_router.include_router(ai.router)
api_router.include_router(tts.router)


@api_router.websocket("/ws/state")
async def ws_state_alias(websocket: WebSocket) -> None:
    """Convenience WebSocket alias matching NEXT_PUBLIC_WS_URL."""
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

