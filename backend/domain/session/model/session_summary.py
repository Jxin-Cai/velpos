from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from domain.session.model.session_status import SessionStatus
from domain.session.model.usage import Usage


@dataclass(frozen=True)
class SessionSummary:
    session_id: str
    project_id: str
    model: str
    status: SessionStatus
    message_count: int
    usage: Usage
    last_input_tokens: int
    project_dir: str
    name: str
    sdk_session_id: str
    updated_time: datetime | None
    card_execution_id: str | None = None
    agent_slot_id: str | None = None
