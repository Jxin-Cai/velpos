from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import datetime

from domain.memory.model.claude_md_revision_state import ClaudeMdRevisionState


_ALLOWED_TRANSITIONS = {
    ClaudeMdRevisionState.DRAFT: {
        ClaudeMdRevisionState.PROPOSED,
        ClaudeMdRevisionState.APPLIED,
        ClaudeMdRevisionState.REJECTED,
    },
    ClaudeMdRevisionState.PROPOSED: {ClaudeMdRevisionState.APPROVED, ClaudeMdRevisionState.REJECTED},
    ClaudeMdRevisionState.APPROVED: {
        ClaudeMdRevisionState.APPLIED,
        ClaudeMdRevisionState.REJECTED,
        ClaudeMdRevisionState.CONFLICTED,
    },
    ClaudeMdRevisionState.CONFLICTED: {ClaudeMdRevisionState.DRAFT, ClaudeMdRevisionState.REJECTED},
}


@dataclass
class ClaudeMdRevision:
    _id: str
    _project_id: str
    _version_no: int
    _state: ClaudeMdRevisionState
    _content: str
    _content_hash: str
    _base_revision_id: str
    _base_file_hash: str
    _created_by: str
    _created_time: datetime = field(default_factory=datetime.now)
    _proposed_time: datetime | None = None
    _approved_time: datetime | None = None
    _applied_time: datetime | None = None
    _rejected_time: datetime | None = None
    _reject_reason: str = ""

    @property
    def id(self) -> str:
        return self._id

    @property
    def project_id(self) -> str:
        return self._project_id

    @property
    def version_no(self) -> int:
        return self._version_no

    @property
    def state(self) -> ClaudeMdRevisionState:
        return self._state

    @property
    def content(self) -> str:
        return self._content

    @property
    def content_hash(self) -> str:
        return self._content_hash

    @property
    def base_revision_id(self) -> str:
        return self._base_revision_id

    @property
    def base_file_hash(self) -> str:
        return self._base_file_hash

    @property
    def created_by(self) -> str:
        return self._created_by

    @property
    def created_time(self) -> datetime:
        return self._created_time

    @property
    def proposed_time(self) -> datetime | None:
        return self._proposed_time

    @property
    def approved_time(self) -> datetime | None:
        return self._approved_time

    @property
    def applied_time(self) -> datetime | None:
        return self._applied_time

    @property
    def rejected_time(self) -> datetime | None:
        return self._rejected_time

    @property
    def reject_reason(self) -> str:
        return self._reject_reason

    @classmethod
    def create_initial(
        cls,
        project_id: str,
        content: str,
        file_hash: str,
    ) -> ClaudeMdRevision:
        return cls(
            _id=uuid.uuid4().hex[:8],
            _project_id=project_id,
            _version_no=1,
            _state=ClaudeMdRevisionState.APPLIED,
            _content=content,
            _content_hash=cls.hash_content(content),
            _base_revision_id="",
            _base_file_hash=file_hash,
            _created_by="system",
            _created_time=datetime.now(),
            _applied_time=datetime.now(),
        )

    @classmethod
    def create_draft(
        cls,
        project_id: str,
        version_no: int,
        content: str,
        base_revision_id: str,
        base_file_hash: str,
        created_by: str = "user",
    ) -> ClaudeMdRevision:
        return cls(
            _id=uuid.uuid4().hex[:8],
            _project_id=project_id,
            _version_no=version_no,
            _state=ClaudeMdRevisionState.DRAFT,
            _content=content,
            _content_hash=cls.hash_content(content),
            _base_revision_id=base_revision_id,
            _base_file_hash=base_file_hash,
            _created_by=created_by,
            _created_time=datetime.now(),
        )

    @classmethod
    def reconstitute(
        cls,
        id: str,
        project_id: str,
        version_no: int,
        state: ClaudeMdRevisionState,
        content: str,
        content_hash: str,
        base_revision_id: str,
        base_file_hash: str,
        created_by: str,
        created_time: datetime,
        proposed_time: datetime | None = None,
        approved_time: datetime | None = None,
        applied_time: datetime | None = None,
        rejected_time: datetime | None = None,
        reject_reason: str = "",
    ) -> ClaudeMdRevision:
        return cls(
            _id=id,
            _project_id=project_id,
            _version_no=version_no,
            _state=state,
            _content=content,
            _content_hash=content_hash,
            _base_revision_id=base_revision_id,
            _base_file_hash=base_file_hash,
            _created_by=created_by,
            _created_time=created_time,
            _proposed_time=proposed_time,
            _approved_time=approved_time,
            _applied_time=applied_time,
            _rejected_time=rejected_time,
            _reject_reason=reject_reason,
        )

    @staticmethod
    def hash_content(content: str) -> str:
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def update_content(self, content: str) -> None:
        if self._state not in {ClaudeMdRevisionState.DRAFT, ClaudeMdRevisionState.CONFLICTED}:
            raise ValueError("Only draft or conflicted revisions can be edited")
        self._content = content
        self._content_hash = self.hash_content(content)

    def propose(self) -> None:
        self._transition_to(ClaudeMdRevisionState.PROPOSED)
        self._proposed_time = datetime.now()

    def approve(self) -> None:
        self._transition_to(ClaudeMdRevisionState.APPROVED)
        self._approved_time = datetime.now()

    def apply(self) -> None:
        self._transition_to(ClaudeMdRevisionState.APPLIED)
        self._applied_time = datetime.now()

    def reject(self, reason: str = "") -> None:
        self._transition_to(ClaudeMdRevisionState.REJECTED)
        self._rejected_time = datetime.now()
        self._reject_reason = reason

    def mark_conflicted(self) -> None:
        self._transition_to(ClaudeMdRevisionState.CONFLICTED)

    def reopen_as_draft(self) -> None:
        self._transition_to(ClaudeMdRevisionState.DRAFT)

    def _transition_to(self, next_state: ClaudeMdRevisionState) -> None:
        if self._state == next_state:
            return
        allowed = _ALLOWED_TRANSITIONS.get(self._state, set())
        if next_state not in allowed:
            raise ValueError(f"Invalid CLAUDE.md revision transition: {self._state.value} -> {next_state.value}")
        self._state = next_state
