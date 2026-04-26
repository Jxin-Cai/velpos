from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class ClaudeMdRevisionEvent:
    id: str
    revision_id: str
    from_state: str
    to_state: str
    payload: dict[str, Any]
    created_time: datetime = field(default_factory=datetime.now)

    @classmethod
    def create(
        cls,
        revision_id: str,
        from_state: str,
        to_state: str,
        payload: dict[str, Any] | None = None,
    ) -> ClaudeMdRevisionEvent:
        return cls(
            id=uuid.uuid4().hex[:8],
            revision_id=revision_id,
            from_state=from_state,
            to_state=to_state,
            payload=dict(payload or {}),
            created_time=datetime.now(),
        )
