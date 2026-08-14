from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from domain.session.model.trace_span import TraceSpan


class ExecutionLedgerEventType(str, Enum):
    SPAN_CREATED = "span_created"
    SPAN_UPDATED = "span_updated"
    SPAN_COMPLETED = "span_completed"
    SPAN_FAILED = "span_failed"
    SPAN_DENIED = "span_denied"
    SPAN_CANCELLED = "span_cancelled"
    SPAN_ABANDONED = "span_abandoned"
    OTEL_LOG = "otel_log"
    OTEL_METRIC = "otel_metric"


_EVENT_TYPE_BY_ACTION = {
    "created": ExecutionLedgerEventType.SPAN_CREATED,
    "updated": ExecutionLedgerEventType.SPAN_UPDATED,
    "completed": ExecutionLedgerEventType.SPAN_COMPLETED,
    "failed": ExecutionLedgerEventType.SPAN_FAILED,
    "denied": ExecutionLedgerEventType.SPAN_DENIED,
    "cancelled": ExecutionLedgerEventType.SPAN_CANCELLED,
    "abandoned": ExecutionLedgerEventType.SPAN_ABANDONED,
}


@dataclass
class ExecutionLedgerEvent:
    event_id: str
    session_id: str
    run_id: str
    event_type: ExecutionLedgerEventType
    span_id: str
    parent_span_id: str | None
    span_type: str
    status: str
    agent_id: str | None
    tool_use_id: str | None
    event_time: datetime
    ingested_time: datetime
    payload: dict[str, Any] = field(default_factory=dict)
    causation_event_id: str | None = None
    position: int | None = None

    @classmethod
    def from_span(cls, span: TraceSpan, action: str) -> ExecutionLedgerEvent:
        event_type = _EVENT_TYPE_BY_ACTION.get(action)
        if event_type is None:
            raise ValueError(f"unsupported execution ledger action: {action}")
        now = datetime.now()
        return cls(
            event_id=uuid.uuid4().hex,
            session_id=span.session_id,
            run_id=span.run_id,
            event_type=event_type,
            span_id=span.id,
            parent_span_id=span.parent_span_id,
            span_type=span.span_type,
            status=span.status,
            agent_id=span.agent_id,
            tool_use_id=span.tool_use_id,
            event_time=now,
            ingested_time=now,
            payload={"action": action, "span": span.to_dict()},
        )

    @classmethod
    def from_otel_record(
        cls,
        *,
        event_id: str,
        session_id: str,
        run_id: str,
        signal: str,
        event_time: datetime,
        payload: dict[str, Any],
        span_id: str = "",
        parent_span_id: str | None = None,
        agent_id: str | None = None,
        tool_use_id: str | None = None,
    ) -> ExecutionLedgerEvent:
        event_type = (
            ExecutionLedgerEventType.OTEL_METRIC
            if signal == "metric"
            else ExecutionLedgerEventType.OTEL_LOG
        )
        return cls(
            event_id=event_id,
            session_id=session_id,
            run_id=run_id,
            event_type=event_type,
            span_id=span_id,
            parent_span_id=parent_span_id,
            span_type=signal,
            status="recorded",
            agent_id=agent_id,
            tool_use_id=tool_use_id,
            event_time=event_time,
            ingested_time=datetime.now(),
            payload=payload,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "sequence": self.position,
            "event_id": self.event_id,
            "session_id": self.session_id,
            "run_id": self.run_id,
            "event_type": self.event_type.value,
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "span_type": self.span_type,
            "status": self.status,
            "agent_id": self.agent_id,
            "tool_use_id": self.tool_use_id,
            "causation_event_id": self.causation_event_id,
            "event_time": self.event_time.isoformat(),
            "ingested_time": self.ingested_time.isoformat(),
            "payload": dict(self.payload),
        }
