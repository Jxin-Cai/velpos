from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class SessionBranch:
    id: str
    source_session_id: str
    branch_session_id: str
    source_message_index: int
    name: str
    root_session_id: str = ""
    group_id: str = ""
    sequence_no: int = 1
    worktree_enabled: bool = False
    worktree_path: str = ""
    base_branch: str = ""
    created_time: datetime = field(default_factory=datetime.now)

    @classmethod
    def create(
        cls,
        source_session_id: str,
        branch_session_id: str,
        source_message_index: int,
        name: str,
        root_session_id: str = "",
        group_id: str = "",
        sequence_no: int = 1,
        worktree_enabled: bool = False,
        worktree_path: str = "",
        base_branch: str = "",
    ) -> SessionBranch:
        return cls(
            id=uuid.uuid4().hex[:8],
            source_session_id=source_session_id,
            branch_session_id=branch_session_id,
            source_message_index=source_message_index,
            name=name,
            root_session_id=root_session_id or source_session_id,
            group_id=group_id or uuid.uuid4().hex[:8],
            sequence_no=sequence_no,
            worktree_enabled=worktree_enabled,
            worktree_path=worktree_path,
            base_branch=base_branch,
            created_time=datetime.now(),
        )
