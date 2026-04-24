from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class SessionAuditEvent:
    id: str
    session_id: str
    event_type: str
    actor: str
    payload: dict[str, Any]
    created_time: datetime

    @classmethod
    def create(
        cls,
        session_id: str,
        event_type: str,
        actor: str = "system",
        payload: dict[str, Any] | None = None,
    ) -> SessionAuditEvent:
        return cls(
            id=uuid.uuid4().hex[:8],
            session_id=session_id,
            event_type=event_type,
            actor=actor,
            payload=dict(payload or {}),
            created_time=datetime.now(),
        )
