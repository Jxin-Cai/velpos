from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import WebSocket

from domain.session.acl.connection_manager import (
    ConnectionManager as ConnectionManagerPort,
)

logger = logging.getLogger(__name__)
_SEND_TIMEOUT_SECONDS = 5.0


class ConnectionManager(ConnectionManagerPort):

    def __init__(self) -> None:
        self._connections: dict[str, list[WebSocket]] = {}
        self._global_connections: list[WebSocket] = []
        self._broadcast_hooks: list[Callable[[str, dict[str, Any]], Awaitable[None]]] = []
        self._lock = asyncio.Lock()

    def register_broadcast_hook(
        self, hook: Callable[[str, dict[str, Any]], Awaitable[None]]
    ) -> None:
        self._broadcast_hooks.append(hook)

    async def connect(self, websocket: WebSocket, session_id: str) -> None:
        await websocket.accept()
        async with self._lock:
            if session_id not in self._connections:
                self._connections[session_id] = []
            self._connections[session_id].append(websocket)

    async def disconnect(self, websocket: WebSocket, session_id: str) -> None:
        async with self._lock:
            if session_id not in self._connections:
                return
            self._connections[session_id] = [
                ws for ws in self._connections[session_id] if ws != websocket
            ]
            if not self._connections[session_id]:
                del self._connections[session_id]

    async def connect_global(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._global_connections.append(websocket)

    async def disconnect_global(self, websocket: WebSocket) -> None:
        async with self._lock:
            self._global_connections = [ws for ws in self._global_connections if ws != websocket]

    @staticmethod
    async def _safe_send(ws: WebSocket, data: dict[str, Any]) -> WebSocket | None:
        try:
            await asyncio.wait_for(
                ws.send_json(data),
                timeout=_SEND_TIMEOUT_SECONDS,
            )
            return None
        except TimeoutError:
            logger.warning(
                "websocket_send_timeout",
                extra={"event": data.get("event", "")},
            )
            return ws
        except Exception:
            logger.warning(
                "websocket_send_failed",
                extra={"event": data.get("event", "")},
                exc_info=True,
            )
            return ws

    async def broadcast_global(self, data: dict[str, Any]) -> None:
        async with self._lock:
            connections = list(self._global_connections)
        if not connections:
            return

        results = await asyncio.gather(*(self._safe_send(ws, data) for ws in connections))
        dead = [ws for ws in results if ws is not None]
        if dead:
            async with self._lock:
                self._global_connections = [ws for ws in self._global_connections if ws not in dead]

    async def broadcast(self, session_id: str, data: dict[str, Any]) -> None:
        async with self._lock:
            connections = list(self._connections.get(session_id, []))
            hooks = list(self._broadcast_hooks)

        if connections:
            results = await asyncio.gather(*(self._safe_send(ws, data) for ws in connections))
            dead = {ws for ws in results if ws is not None}
            if dead:
                async with self._lock:
                    if session_id in self._connections:
                        self._connections[session_id] = [ws for ws in self._connections[session_id] if ws not in dead]
                        if not self._connections[session_id]:
                            del self._connections[session_id]

        if hooks:
            await asyncio.gather(
                *(self._safe_hook(hook, session_id, data) for hook in hooks)
            )

    @staticmethod
    async def _safe_hook(
        hook: Callable[[str, dict[str, Any]], Awaitable[None]],
        session_id: str,
        data: dict[str, Any],
    ) -> None:
        try:
            await hook(session_id, data)
        except Exception:
            logger.warning(
                "Broadcast hook failed for session %s", session_id, exc_info=True
            )

    async def has_connections(self, session_id: str) -> bool:
        async with self._lock:
            return session_id in self._connections
