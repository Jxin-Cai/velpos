from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class ProjectionCompleteness(str, Enum):
    COMPLETE = "complete"
    PARTIAL = "partial"


class ExecutionEventType(str, Enum):
    MODEL_INPUT = "model_input"
    MODEL_OUTPUT = "model_output"
    TOOL_USE = "tool_use"
    TOOL_RESULT = "tool_result"
    SUBAGENT = "subagent"
    THINKING = "thinking"


@dataclass(frozen=True)
class ProjectionProvenance:
    reconstructed_from_transcript: bool = True
    completeness: ProjectionCompleteness = ProjectionCompleteness.COMPLETE
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class ExecutionEvent:
    type: ExecutionEventType
    source_uuid: str | None
    content: Any = None
    tool_use_id: str | None = None
    tool_name: str | None = None
    is_error: bool = False
    error_message: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime | None = None


@dataclass(frozen=True)
class SubagentPlaceholder:
    tool_use_id: str
    subagent: str | None
    agent_id: str | None
    transcript_path: str | None
    span_id: str | None

    @property
    def is_expandable(self) -> bool:
        return self.span_id is not None


@dataclass(frozen=True)
class AgentLoop:
    id: str
    task_id: str
    model_input: tuple[dict[str, Any], ...]
    assistant_content: tuple[Any, ...]
    events: tuple[ExecutionEvent, ...]
    model: str | None
    stop_reason: str | None
    usage: dict[str, Any]
    provenance: ProjectionProvenance
    started_time: datetime | None = None
    ended_time: datetime | None = None
    duration_ms: int = 0
    error_message: str | None = None
    sequence: int = 0

    @property
    def subagent_count(self) -> int:
        return sum(1 for e in self.events if e.type == ExecutionEventType.SUBAGENT)

    @property
    def subagent_tool_use_ids(self) -> tuple[str, ...]:
        return tuple(
            e.metadata.get("tool_use_id")
            for e in self.events
            if e.type == ExecutionEventType.SUBAGENT and e.metadata.get("tool_use_id")
        )

    @property
    def subagents(self) -> tuple[dict[str, Any], ...]:
        """Agent calls belonging to this loop, kept with their parent task."""
        return tuple(
            {
                **event.metadata,
                "tool_use_id": event.metadata.get("tool_use_id") or event.tool_use_id,
                "subagent": event.metadata.get("subagent"),
                "span_id": event.metadata.get("span_id"),
                "agent_id": event.metadata.get("agent_id"),
                "transcript_path": event.metadata.get("transcript_path"),
                "is_expandable": bool(event.metadata.get("span_id")),
            }
            for event in self.events
            if event.type == ExecutionEventType.SUBAGENT
        )

    @property
    def tool_names(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(
            event.tool_name
            for event in self.events
            if event.type == ExecutionEventType.TOOL_USE
            and event.tool_name
            and event.tool_name not in {"TaskCreate", "TaskUpdate"}
        ))

    def detail_page(self, cursor: int = 0, limit: int = 100) -> LoopDetailPage:
        if cursor < 0:
            raise ValueError("cursor must be non-negative")
        if limit <= 0:
            raise ValueError("limit must be positive")
        items = self.events[cursor : cursor + limit]
        end = cursor + len(items)
        return LoopDetailPage(items, end if end < len(self.events) else None, len(self.events))


@dataclass(frozen=True)
class LoopDetailPage:
    items: tuple[ExecutionEvent, ...]
    next_cursor: int | None
    total: int


@dataclass(frozen=True)
class TaskDependency:
    task_id: str
    depends_on_task_id: str


@dataclass(frozen=True)
class ExecutionTask:
    id: str
    subject: str
    description: str | None
    status: str
    explicit: bool
    loops: tuple[AgentLoop, ...]


@dataclass(frozen=True)
class ExecutionAgent:
    id: str
    tasks: tuple[ExecutionTask, ...]
    dependencies: tuple[TaskDependency, ...]
    subagents: tuple[SubagentPlaceholder, ...]
    provenance: ProjectionProvenance
    request: Any = None
