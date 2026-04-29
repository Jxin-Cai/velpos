from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class SessionTimelineEvent:
    id: str
    session_id: str
    run_id: str
    seq: int
    event_type: str
    status: str
    title: str
    payload: dict[str, Any] = field(default_factory=dict)
    started_time: datetime = field(default_factory=datetime.now)
    ended_time: datetime | None = None
    duration_ms: int = 0
    created_time: datetime = field(default_factory=datetime.now)

    @classmethod
    def create(
        cls,
        session_id: str,
        run_id: str,
        seq: int,
        event_type: str,
        title: str,
        payload: dict[str, Any] | None = None,
        status: str = "completed",
    ) -> SessionTimelineEvent:
        now = datetime.now()
        return cls(
            id=uuid.uuid4().hex[:12],
            session_id=session_id,
            run_id=run_id or "external",
            seq=max(seq, 1),
            event_type=event_type,
            status=status,
            title=title,
            payload=dict(payload or {}),
            started_time=now,
            ended_time=now if status in {"completed", "failed", "cancelled"} else None,
            created_time=now,
        )
