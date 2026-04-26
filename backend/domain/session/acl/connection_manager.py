from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class ConnectionManager(ABC):

    @abstractmethod
    async def broadcast(self, session_id: str, data: dict[str, Any]) -> None:
        """Broadcast a message to all WebSocket connections for the given session.

        Silently returns if there are no active connections for the session.
        Connections that fail to receive should be automatically cleaned up.
        """
        ...

    @abstractmethod
    async def broadcast_global(self, data: dict[str, Any]) -> None:
        """Broadcast a message to global WebSocket event subscribers."""
        ...

    @abstractmethod
    def has_connections(self, session_id: str) -> bool:
        """Check if a session has any active WebSocket connections."""
        ...
