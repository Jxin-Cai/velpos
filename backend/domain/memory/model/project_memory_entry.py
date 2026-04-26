from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class ProjectMemoryEntry:
    id: str
    project_id: str
    memory_type: str
    title: str
    content: str
    source_session_id: str = ""
    source_message_id: str = ""
    visibility: str = "project"
    state: str = "active"
    created_time: datetime = field(default_factory=datetime.now)
    updated_time: datetime = field(default_factory=datetime.now)

    @classmethod
    def create(
        cls,
        project_id: str,
        memory_type: str,
        title: str,
        content: str,
        source_session_id: str = "",
        source_message_id: str = "",
        visibility: str = "project",
    ) -> ProjectMemoryEntry:
        return cls(
            id=uuid.uuid4().hex[:8],
            project_id=project_id,
            memory_type=memory_type or "note",
            title=title.strip(),
            content=content,
            source_session_id=source_session_id,
            source_message_id=source_message_id,
            visibility=visibility or "project",
            state="active",
            created_time=datetime.now(),
            updated_time=datetime.now(),
        )

    def update(
        self,
        title: str | None = None,
        content: str | None = None,
        memory_type: str | None = None,
        visibility: str | None = None,
        state: str | None = None,
    ) -> None:
        if title is not None:
            self.title = title.strip()
        if content is not None:
            self.content = content
        if memory_type is not None:
            self.memory_type = memory_type or "note"
        if visibility is not None:
            self.visibility = visibility or "project"
        if state is not None:
            self.state = state or "active"
        self.updated_time = datetime.now()
