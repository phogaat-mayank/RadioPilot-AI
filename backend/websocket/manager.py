"""Connected dashboard WebSocket management."""

import asyncio
import logging
from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Safely broadcast real-time station state to dashboards."""

    def __init__(self) -> None:
        """Create an empty connection registry."""
        self._connections: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket) -> None:
        """Accept and track a dashboard connection."""
        await websocket.accept()
        async with self._lock:
            self._connections.add(websocket)

    async def disconnect(self, websocket: WebSocket) -> None:
        """Remove a closed dashboard connection."""
        async with self._lock:
            self._connections.discard(websocket)

    async def broadcast(self, payload: dict) -> None:
        """Send a state payload to every currently connected client."""
        async with self._lock:
            targets = list(self._connections)
        for websocket in targets:
            try:
                await websocket.send_json(payload)
            except Exception:
                logger.info("Removing closed dashboard websocket")
                await self.disconnect(websocket)


manager = ConnectionManager()
