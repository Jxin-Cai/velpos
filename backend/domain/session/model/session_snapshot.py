from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class SessionSnapshot:
    id: str
    session_id: str
    message_index: int
    messages: list[dict[str, Any]]
    created_time: datetime = field(default_factory=datetime.now)

    @classmethod
    def create(
        cls,
        session_id: str,
        message_index: int,
        messages: list[dict[str, Any]],
    ) -> SessionSnapshot:
        return cls(
            id=uuid.uuid4().hex[:8],
            session_id=session_id,
            message_index=message_index,
            messages=list(messages),
            created_time=datetime.now(),
        )
