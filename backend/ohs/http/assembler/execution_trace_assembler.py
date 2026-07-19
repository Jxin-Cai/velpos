from __future__ import annotations

from domain.session.model.execution_trace import (
    AgentLoop,
    ExecutionAgent,
    ExecutionEvent,
    ExecutionTask,
    LoopDetailPage,
    ProjectionProvenance,
    SubagentPlaceholder,
    TaskDependency,
)
from ohs.http.dto.execution_trace_dto import (
    ExecutionEventDto,
    ExecutionTaskDto,
    ExecutionTreeResponse,
    LoopDetailPageResponse,
    LoopDto,
    ProvenanceDto,
    SubagentPlaceholderDto,
    TaskDependencyDto,
)


class ExecutionTraceAssembler:
    """Converts execution trace domain models to response DTOs."""

    @staticmethod
    def to_tree_response(agent: ExecutionAgent) -> ExecutionTreeResponse:
        return ExecutionTreeResponse(
            agent_id=agent.id,
            tasks=[ExecutionTraceAssembler._to_task_dto(t) for t in agent.tasks],
            dependencies=[ExecutionTraceAssembler._to_dependency_dto(d) for d in agent.dependencies],
            subagents=[ExecutionTraceAssembler._to_subagent_dto(s) for s in agent.subagents],
            provenance=ExecutionTraceAssembler._to_provenance_dto(agent.provenance),
        )

    @staticmethod
    def to_loop_detail_response(page: LoopDetailPage) -> LoopDetailPageResponse:
        return LoopDetailPageResponse(
            items=[ExecutionTraceAssembler._to_event_dto(e) for e in page.items],
            next_cursor=page.next_cursor,
            total=page.total,
        )

    @staticmethod
    def _to_task_dto(task: ExecutionTask) -> ExecutionTaskDto:
        return ExecutionTaskDto(
            id=task.id,
            subject=task.subject,
            description=task.description,
            status=task.status,
            explicit=task.explicit,
            loops=[
                ExecutionTraceAssembler._to_loop_dto(loop, sequence)
                for sequence, loop in enumerate(task.loops, start=1)
            ],
            thinking=list(task.thinking),
        )

    @staticmethod
    def _to_loop_dto(loop: AgentLoop, sequence: int) -> LoopDto:
        return LoopDto(
            id=loop.id,
            task_id=loop.task_id,
            sequence=sequence,
            event_count=len(loop.events),
            model=loop.model,
            stop_reason=loop.stop_reason,
            usage=loop.usage,
            subagent_count=loop.subagent_count,
            subagent_tool_use_ids=list(loop.subagent_tool_use_ids),
            tool_names=list(loop.tool_names),
            subagents=list(loop.subagents),
            started_time=loop.started_time,
            ended_time=loop.ended_time,
            duration_ms=loop.duration_ms,
        )

    @staticmethod
    def _to_dependency_dto(dep: TaskDependency) -> TaskDependencyDto:
        return TaskDependencyDto(
            task_id=dep.task_id,
            depends_on_task_id=dep.depends_on_task_id,
        )

    @staticmethod
    def _to_subagent_dto(sub: SubagentPlaceholder) -> SubagentPlaceholderDto:
        return SubagentPlaceholderDto(
            tool_use_id=sub.tool_use_id,
            subagent=sub.subagent,
            agent_id=sub.agent_id,
            transcript_path=sub.transcript_path,
            span_id=sub.span_id,
            is_expandable=sub.is_expandable,
        )

    @staticmethod
    def _to_provenance_dto(prov: ProjectionProvenance) -> ProvenanceDto:
        return ProvenanceDto(
            reconstructed_from_transcript=prov.reconstructed_from_transcript,
            completeness=prov.completeness.value,
            warnings=list(prov.warnings),
        )

    @staticmethod
    def _to_event_dto(event: ExecutionEvent) -> ExecutionEventDto:
        return ExecutionEventDto(
            type=event.type.value,
            source_uuid=event.source_uuid,
            content=event.content,
            tool_use_id=event.tool_use_id,
            tool_name=event.tool_name,
            is_error=event.is_error,
            metadata=event.metadata,
            timestamp=event.timestamp,
        )
