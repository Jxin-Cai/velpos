from __future__ import annotations

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
    event_count: int
    model: str | None = None
    stop_reason: str | None = None
    usage: dict[str, Any] = Field(default_factory=dict)


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


class ProvenanceDto(BaseModel):
    reconstructed_from_transcript: bool = True
    completeness: str = "complete"
    warnings: list[str] = Field(default_factory=list)


class ExecutionTreeResponse(BaseModel):
    agent_id: str
    tasks: list[ExecutionTaskDto] = Field(default_factory=list)
    dependencies: list[TaskDependencyDto] = Field(default_factory=list)
    subagents: list[SubagentPlaceholderDto] = Field(default_factory=list)
    provenance: ProvenanceDto


class LoopDetailPageResponse(BaseModel):
    items: list[ExecutionEventDto] = Field(default_factory=list)
    next_cursor: int | None = None
    total: int = 0
