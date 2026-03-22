"""WebSocket connection manager and /ws/{user_id} endpoint."""
from __future__ import annotations

import logging
from collections import defaultdict
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

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


# Singleton instance shared across the application
ws_manager = WebSocketManager()


# ---------------------------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------------------------


@ws_router.websocket("/ws/{user_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    user_id: str,
    token: Optional[str] = None,
) -> None:
    """Accept a WebSocket connection.

    Auth supports two modes:
    - Cookie-based (local dev): Civic Auth cookie read automatically
    - Bearer token (deployed): pass ?token=<id_token> as query param
    """
    from backend.auth import CivicAuth, MemoryStorage, _config

    # Build storage from token query param or cookies
    if token:
        mem = MemoryStorage({CivicAuth.ID_TOKEN_KEY: token})
    else:
        # Fall back to cookies (local dev)
        mem = MemoryStorage({k: v for k, v in websocket.cookies.items()})

    civic = CivicAuth(mem, _config)

    try:
        user = await civic.get_user()
        if not user or user.get("id") != user_id:
            await websocket.close(code=4001)
            return
    except Exception:
        await websocket.close(code=4001)
        return

    await ws_manager.connect(user_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(user_id, websocket)
