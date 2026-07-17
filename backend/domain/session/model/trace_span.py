from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class TraceSpan:
    id: str
    session_id: str
    run_id: str
    parent_span_id: str | None
    span_type: str
    name: str
    status: str
    agent_id: str | None
    tool_use_id: str | None
    input_preview: str | None
    output_preview: str | None
    metadata: dict[str, Any] = field(default_factory=dict)
    started_time: datetime = field(default_factory=datetime.now)
    ended_time: datetime | None = None
    duration_ms: int = 0
    created_time: datetime = field(default_factory=datetime.now)

    SPAN_TYPE_LLM_TURN = "llm_turn"
    SPAN_TYPE_TOOL_CALL = "tool_call"
    SPAN_TYPE_AGENT = "agent"
    SPAN_TYPE_SUBAGENT = "subagent"
    SPAN_TYPE_RUN = "run"

    STATUS_RUNNING = "running"
    STATUS_COMPLETED = "completed"
    STATUS_FAILED = "failed"
    STATUS_DENIED = "denied"
    STATUS_CANCELLED = "cancelled"

    @classmethod
    def create(
        cls,
        session_id: str,
        run_id: str,
        span_type: str,
        name: str,
        parent_span_id: str | None = None,
        agent_id: str | None = None,
        tool_use_id: str | None = None,
        input_preview: str | None = None,
        output_preview: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> TraceSpan:
        now = datetime.now()
        return cls(
            id=uuid.uuid4().hex[:16],
            session_id=session_id,
            run_id=run_id,
            parent_span_id=parent_span_id,
            span_type=span_type,
            name=name,
            status=cls.STATUS_RUNNING,
            agent_id=agent_id,
            tool_use_id=tool_use_id,
            input_preview=input_preview,
            output_preview=output_preview,
            metadata=dict(metadata or {}),
            started_time=now,
            ended_time=None,
            duration_ms=0,
            created_time=now,
        )

    def complete(self, output_preview: str | None = None, metadata: dict[str, Any] | None = None) -> None:
        self.status = self.STATUS_COMPLETED
        # A turn gets its assistant preview when it is created, then is closed by
        # the next stream event or Stop hook.  Do not erase that useful payload
        # when the closing event has no additional output.
        if output_preview is not None:
            self.output_preview = output_preview
        if metadata:
            self.metadata.update(metadata)
        self.ended_time = datetime.now()
        self.duration_ms = max(int((self.ended_time - self.started_time).total_seconds() * 1000), 0)

    def fail(self, error: str | None = None, metadata: dict[str, Any] | None = None) -> None:
        self.status = self.STATUS_FAILED
        if error:
            self.metadata["error"] = error
        if metadata:
            self.metadata.update(metadata)
        self.ended_time = datetime.now()
        self.duration_ms = max(int((self.ended_time - self.started_time).total_seconds() * 1000), 0)

    def deny(self, reason: str | None = None) -> None:
        self.status = self.STATUS_DENIED
        if reason:
            self.metadata["deny_reason"] = reason
        self.ended_time = datetime.now()
        self.duration_ms = max(int((self.ended_time - self.started_time).total_seconds() * 1000), 0)

    def cancel(self, reason: str | None = None) -> None:
        self.status = self.STATUS_CANCELLED
        if reason:
            self.metadata["cancel_reason"] = reason
        self.ended_time = datetime.now()
        self.duration_ms = max(int((self.ended_time - self.started_time).total_seconds() * 1000), 0)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "run_id": self.run_id,
            "parent_span_id": self.parent_span_id,
            "span_type": self.span_type,
            "name": self.name,
            "status": self.status,
            "agent_id": self.agent_id,
            "tool_use_id": self.tool_use_id,
            "input_preview": self.input_preview,
            "output_preview": self.output_preview,
            "metadata": dict(self.metadata),
            "started_time": self.started_time.isoformat() if self.started_time else None,
            "ended_time": self.ended_time.isoformat() if self.ended_time else None,
            "duration_ms": self.duration_ms,
        }
