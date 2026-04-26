from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class Attachment:
    id: str
    project_id: str
    session_id: str
    filename: str
    mime_type: str
    size_bytes: int
    storage_path: str
    sha256: str
    created_time: datetime = field(default_factory=datetime.now)

    @staticmethod
    def create(
        project_id: str,
        session_id: str,
        filename: str,
        mime_type: str,
        size_bytes: int,
        storage_path: str,
        sha256: str,
    ) -> "Attachment":
        if not session_id:
            raise ValueError("session_id is required")
        if not filename:
            raise ValueError("filename is required")
        if size_bytes < 0:
            raise ValueError("size_bytes must be >= 0")
        return Attachment(
            id=uuid.uuid4().hex[:8],
            project_id=project_id,
            session_id=session_id,
            filename=filename,
            mime_type=mime_type or "application/octet-stream",
            size_bytes=size_bytes,
            storage_path=storage_path,
            sha256=sha256,
        )

    def to_message_ref(self) -> dict:
        return {
            "id": self.id,
            "filename": self.filename,
            "mime_type": self.mime_type,
            "size_bytes": self.size_bytes,
            "path": self.storage_path,
            "sha256": self.sha256,
        }
