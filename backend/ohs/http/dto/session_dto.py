from __future__ import annotations

import os
from typing import Any

from pydantic import BaseModel, Field

from domain.session.model.session import Session
from domain.session.model.session_audit_event import SessionAuditEvent
from ohs.assembler.session_assembler import SessionAssembler

_DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "claude-opus-4-6")


class CreateSessionRequest(BaseModel):
    model: str = Field(
        default=_DEFAULT_MODEL,
        min_length=1,
        max_length=100,
        description="Claude model identifier",
    )
    project_id: str = Field(
        default="",
        max_length=8,
        description="Project ID this session belongs to",
    )
    name: str = Field(
        default="",
        max_length=200,
        description="Project name (auto-creates dir under PROJECTS_ROOT_DIR)",
    )
    project_dir: str = Field(
        default="",
        max_length=500,
        description="Full project directory path (overrides name-based creation)",
    )


class RenameSessionRequest(BaseModel):
    name: str = Field(
        min_length=1,
        max_length=200,
        description="New session name",
    )


class ImportClaudeSessionRequest(BaseModel):
    claude_session_id: str = Field(
        min_length=1,
        description="Claude Code session UUID",
    )
    cwd: str = Field(
        default="",
        description="Project directory (cwd)",
    )
    name: str = Field(
        default="",
        description="Session name",
    )


class BatchDeleteRequest(BaseModel):
    session_ids: list[str] = Field(
        min_length=1,
        description="List of session IDs to delete",
    )


class SessionResponse(BaseModel):
    session_id: str
    project_id: str
    model: str
    status: str
    message_count: int
    usage: dict[str, int]
    project_dir: str
    name: str
    sdk_session_id: str = ""
    updated_time: str | None = None
    source: str = ""
    im_binding: dict | None = None

    @classmethod
    def from_domain(
        cls,
        session: Session,
        binding_info: dict | None = None,
    ) -> SessionResponse:
        summary = SessionAssembler.to_summary(session)
        return cls(
            session_id=summary["session_id"],
            project_id=summary["project_id"],
            model=summary["model"],
            status=summary["status"],
            message_count=summary["message_count"],
            usage=summary["usage"],
            project_dir=summary["project_dir"],
            name=summary["name"],
            sdk_session_id=summary.get("sdk_session_id", ""),
            updated_time=summary["updated_time"],
            source=summary.get("source", ""),
            im_binding=binding_info,
        )


class SessionListResponse(BaseModel):
    sessions: list[SessionResponse]

    @classmethod
    def from_domain_list(
        cls,
        sessions: list[Session],
        binding_map: dict | None = None,
    ) -> SessionListResponse:
        binding_map = binding_map or {}
        return cls(
            sessions=[
                SessionResponse.from_domain(s, binding_map.get(s.session_id))
                for s in sessions
            ],
        )


class SessionDetailResponse(BaseModel):
    session_id: str
    project_id: str
    model: str
    status: str
    message_count: int
    usage: dict[str, int]
    project_dir: str
    name: str
    updated_time: str | None
    messages: list[dict[str, Any]]

    @classmethod
    def from_domain(cls, session: Session) -> SessionDetailResponse:
        summary = SessionAssembler.to_summary(session)
        return cls(
            session_id=summary["session_id"],
            project_id=summary["project_id"],
            model=summary["model"],
            status=summary["status"],
            message_count=summary["message_count"],
            usage=summary["usage"],
            project_dir=summary["project_dir"],
            name=summary["name"],
            updated_time=summary["updated_time"],
            messages=[SessionAssembler.message_to_dict(msg) for msg in session.messages],
        )


class SessionArtifactResponse(BaseModel):
    id: str
    path: str
    label: str
    source_message_index: int
    message_type: str


class SessionArtifactListResponse(BaseModel):
    artifacts: list[SessionArtifactResponse]

    @classmethod
    def from_dict_list(cls, artifacts: list[dict[str, Any]]) -> SessionArtifactListResponse:
        return cls(artifacts=[SessionArtifactResponse(**item) for item in artifacts])


class SessionAuditEventResponse(BaseModel):
    id: str
    session_id: str
    event_type: str
    actor: str
    payload: dict[str, Any]
    created_time: str

    @classmethod
    def from_domain(cls, event: SessionAuditEvent) -> SessionAuditEventResponse:
        return cls(
            id=event.id,
            session_id=event.session_id,
            event_type=event.event_type,
            actor=event.actor,
            payload=event.payload,
            created_time=event.created_time.isoformat(),
        )


class SessionAuditEventListResponse(BaseModel):
    events: list[SessionAuditEventResponse]

    @classmethod
    def from_domain_list(
        cls,
        events: list[SessionAuditEvent],
    ) -> SessionAuditEventListResponse:
        return cls(events=[SessionAuditEventResponse.from_domain(e) for e in events])
