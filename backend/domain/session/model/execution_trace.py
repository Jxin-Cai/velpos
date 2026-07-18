from __future__ import annotations

from dataclasses import dataclass, field
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
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SubagentPlaceholder:
    tool_use_id: str
    subagent: str | None
    agent_id: str | None
    transcript_path: str | None
    span_id: str | None

    @property
    def is_expandable(self) -> bool:
        return self.transcript_path is not None


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
