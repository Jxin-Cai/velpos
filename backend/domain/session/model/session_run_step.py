from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class SessionRunStep:
    id: str
    session_id: str
    run_id: str
    step_type: str
    status: str
    title: str
    payload: dict[str, Any] = field(default_factory=dict)
    started_time: datetime = field(default_factory=datetime.now)
    ended_time: datetime | None = None
    duration_ms: int = 0

    @classmethod
    def start(
        cls,
        session_id: str,
        run_id: str,
        step_type: str,
        title: str,
        payload: dict[str, Any] | None = None,
    ) -> SessionRunStep:
        return cls(
            id=uuid.uuid4().hex[:8],
            session_id=session_id,
            run_id=run_id,
            step_type=step_type,
            status="running",
            title=title,
            payload=dict(payload or {}),
            started_time=datetime.now(),
        )

    def progress(self, payload: dict[str, Any] | None = None) -> None:
        if payload:
            self.payload.update(payload)

    def complete(self, payload: dict[str, Any] | None = None) -> None:
        self._finish("completed", payload)

    def fail(self, payload: dict[str, Any] | None = None) -> None:
        self._finish("failed", payload)

    def _finish(self, status: str, payload: dict[str, Any] | None = None) -> None:
        self.status = status
        if payload:
            self.payload.update(payload)
        self.ended_time = datetime.now()
        self.duration_ms = max(int((self.ended_time - self.started_time).total_seconds() * 1000), 0)
