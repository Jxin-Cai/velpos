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


class ConnectionManager(ConnectionManagerPort):

    def __init__(self) -> None:
        self._connections: dict[str, list[WebSocket]] = {}
        self._global_connections: list[WebSocket] = []
        self._broadcast_hooks: list[Callable[[str, dict[str, Any]], Awaitable[None]]] = []

    def register_broadcast_hook(
        self, hook: Callable[[str, dict[str, Any]], Awaitable[None]]
    ) -> None:
        self._broadcast_hooks.append(hook)

    async def connect(self, websocket: WebSocket, session_id: str) -> None:
        await websocket.accept()
        if session_id not in self._connections:
            self._connections[session_id] = []
        self._connections[session_id].append(websocket)

    def disconnect(self, websocket: WebSocket, session_id: str) -> None:
        if session_id not in self._connections:
            return
        self._connections[session_id] = [
            ws for ws in self._connections[session_id] if ws != websocket
        ]
        if not self._connections[session_id]:
            del self._connections[session_id]

    async def connect_global(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self._global_connections.append(websocket)

    def disconnect_global(self, websocket: WebSocket) -> None:
        self._global_connections = [ws for ws in self._global_connections if ws != websocket]

    async def broadcast_global(self, data: dict[str, Any]) -> None:
        connections = list(self._global_connections)
        if not connections:
            return

        async def _safe_send(ws: WebSocket) -> WebSocket | None:
            try:
                await ws.send_json(data)
                return None
            except Exception:
                return ws

        results = await asyncio.gather(*(_safe_send(ws) for ws in connections))
        dead = [ws for ws in results if ws is not None]
        for ws in dead:
            if ws in self._global_connections:
                self._global_connections.remove(ws)

    async def broadcast(self, session_id: str, data: dict[str, Any]) -> None:
        connections = list(self._connections.get(session_id, []))

        async def _safe_send(ws: WebSocket) -> WebSocket | None:
            try:
                await ws.send_json(data)
                return None
            except Exception:
                return ws

        if connections:
            results = await asyncio.gather(*(_safe_send(ws) for ws in connections))
            dead = [ws for ws in results if ws is not None]
            for ws in dead:
                if ws in self._connections.get(session_id, []):
                    self._connections[session_id].remove(ws)
            if session_id in self._connections and not self._connections[session_id]:
                del self._connections[session_id]

        if self._broadcast_hooks:
            await asyncio.gather(
                *(self._safe_hook(hook, session_id, data) for hook in self._broadcast_hooks)
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

    def has_connections(self, session_id: str) -> bool:
        return session_id in self._connections
