from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ExecutionEventDto(BaseModel):
    type: str
    source_uuid: str | None = None
    content: Any = None
    tool_use_id: str | None = None
    tool_name: str | None = None
    is_error: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime | None = None


class SubagentPlaceholderDto(BaseModel):
    tool_use_id: str
    subagent: str | None = None
    agent_id: str | None = None
    transcript_path: str | None = None
    span_id: str | None = None
    is_expandable: bool = False


class LoopDto(BaseModel):
    id: str
    task_id: str
    sequence: int
    event_count: int
    model: str | None = None
    stop_reason: str | None = None
    usage: dict[str, Any] = Field(default_factory=dict)
    subagent_count: int = 0
    subagent_tool_use_ids: list[str] = Field(default_factory=list)
    tool_names: list[str] = Field(default_factory=list)
    subagents: list[dict[str, Any]] = Field(default_factory=list)
    started_time: datetime | None = None
    ended_time: datetime | None = None
    duration_ms: int = 0


class TaskDependencyDto(BaseModel):
    task_id: str
    depends_on_task_id: str


class ExecutionTaskDto(BaseModel):
    id: str
    subject: str
    description: str | None = None
    status: str
    explicit: bool
    loops: list[LoopDto] = Field(default_factory=list)
    thinking: list[dict[str, Any]] = Field(default_factory=list)


class ProvenanceDto(BaseModel):
    reconstructed_from_transcript: bool = True
    completeness: str = "complete"
    warnings: list[str] = Field(default_factory=list)


class ExecutionTreeResponse(BaseModel):
    agent_id: str
    request: Any = None
    tasks: list[ExecutionTaskDto] = Field(default_factory=list)
    dependencies: list[TaskDependencyDto] = Field(default_factory=list)
    subagents: list[SubagentPlaceholderDto] = Field(default_factory=list)
    provenance: ProvenanceDto


class LoopDetailPageResponse(BaseModel):
    items: list[ExecutionEventDto] = Field(default_factory=list)
    next_cursor: int | None = None
    total: int = 0
