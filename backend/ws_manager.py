"""WebSocket connection manager and /ws/{user_id} endpoint."""
from __future__ import annotations

import logging
from collections import defaultdict

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from backend.models import WSEvent

logger = logging.getLogger(__name__)

ws_router = APIRouter()


class WebSocketManager:
    """In-memory manager for per-user WebSocket connections."""

    def __init__(self) -> None:
        # user_id → set of active WebSocket connections
        self._connections: dict[str, set[WebSocket]] = defaultdict(set)

    async def connect(self, user_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections[user_id].add(websocket)
        logger.debug("WS connected: user=%s total=%d", user_id, len(self._connections[user_id]))

    def disconnect(self, user_id: str, websocket: WebSocket) -> None:
        self._connections[user_id].discard(websocket)
        if not self._connections[user_id]:
            del self._connections[user_id]
        logger.debug("WS disconnected: user=%s", user_id)

    async def broadcast_to_user(self, user_id: str, event: WSEvent) -> None:
        """Send an event to all connections for a specific user."""
        dead: list[WebSocket] = []
        for ws in list(self._connections.get(user_id, [])):
            try:
                await ws.send_text(event.model_dump_json())
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(user_id, ws)

    async def broadcast_all(self, event: WSEvent) -> None:
        """Send an event to every connected user."""
        for user_id in list(self._connections.keys()):
            await self.broadcast_to_user(user_id, event)


# Singleton instance shared across the application
ws_manager = WebSocketManager()


# ---------------------------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------------------------


@ws_router.websocket("/ws/{user_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    user_id: str,
    token: str = Query(...),
) -> None:
    """Accept a WebSocket connection after validating the Civic token."""
    from backend.auth import verify_civic_token  # avoid circular import at module level

    try:
        user = await verify_civic_token(token)
        if user.get("id") != user_id:
            await websocket.close(code=4001)
            return
    except Exception:
        await websocket.close(code=4001)
        return

    await ws_manager.connect(user_id, websocket)
    try:
        while True:
            # Keep connection alive; clients send no messages in this design
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(user_id, websocket)
