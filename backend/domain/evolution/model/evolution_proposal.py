from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class EvolutionProposal:
    id: str
    project_id: str
    source_session_id: str
    state: str
    extracted_lessons: list[dict[str, Any]] = field(default_factory=list)
    proposed_claude_md_revision_id: str = ""
    created_time: datetime = field(default_factory=datetime.now)
    updated_time: datetime = field(default_factory=datetime.now)

    @staticmethod
    def create(project_id: str, source_session_id: str, lessons: list[dict[str, Any]]) -> "EvolutionProposal":
        return EvolutionProposal(
            id=uuid.uuid4().hex[:8],
            project_id=project_id,
            source_session_id=source_session_id,
            state="extracted",
            extracted_lessons=list(lessons),
        )

    def attach_revision(self, revision_id: str) -> None:
        self.proposed_claude_md_revision_id = revision_id
        self.state = "proposed"
        self.updated_time = datetime.now()

    def approve(self) -> None:
        self.state = "approved"
        self.updated_time = datetime.now()

    def reject(self) -> None:
        self.state = "rejected"
        self.updated_time = datetime.now()
