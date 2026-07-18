from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Iterable, Mapping

from domain.session.model.execution_trace import (
    AgentLoop,
    ExecutionAgent,
    ExecutionEvent,
    ExecutionEventType,
    ExecutionTask,
    ProjectionCompleteness,
    ProjectionProvenance,
    SubagentPlaceholder,
    TaskDependency,
)
from domain.session.model.trace_span import TraceSpan


@dataclass
class _TaskState:
    id: str
    subject: str
    explicit: bool
    description: str | None = None
    status: str = "pending"
    loops: list[AgentLoop] = field(default_factory=list)


class ExecutionTraceProjector:
    """Pure projection from parsed transcript records and existing trace spans."""

    IMPLICIT_TASK_ID = "implicit-user-task"

    def project(
        self,
        records: Iterable[Mapping[str, Any]],
        spans: Iterable[TraceSpan] = (),
        agent_id: str = "main",
    ) -> ExecutionAgent:
        span_by_tool = {span.tool_use_id: span for span in spans if span.tool_use_id}
        tasks = {self.IMPLICIT_TASK_ID: _TaskState(self.IMPLICIT_TASK_ID, "User request", False, status="in_progress")}
        dependencies: list[TaskDependency] = []
        subagents: list[SubagentPlaceholder] = []
        loops: list[AgentLoop] = []
        pending: dict[str, int] = {}
        history: list[dict[str, Any]] = []
        warnings: list[str] = []

        for record in records:
            message = record.get("message")
            if not isinstance(message, Mapping):
                continue
            role = message.get("role") or record.get("type")
            blocks = self._content_blocks(message.get("content"), warnings)
            source_uuid = self._text(record.get("uuid"))
            if role == "assistant":
                task_id = self._active_task(tasks, warnings)
                events = [
                    ExecutionEvent(ExecutionEventType.MODEL_INPUT, source_uuid, tuple(history)),
                    ExecutionEvent(ExecutionEventType.MODEL_OUTPUT, source_uuid, tuple(blocks)),
                ]
                loop_index = len(loops)
                for block in blocks:
                    if not isinstance(block, Mapping) or block.get("type") != "tool_use":
                        continue
                    tool_id = self._text(block.get("id"))
                    tool_name = self._text(block.get("name"))
                    if not tool_id:
                        warnings.append("tool_use_missing_id")
                        continue
                    events.append(ExecutionEvent(ExecutionEventType.TOOL_USE, source_uuid, block.get("input"), tool_id, tool_name))
                    pending[tool_id] = loop_index
                    if tool_name in {"TaskCreate", "TaskUpdate"}:
                        self._apply_task_tool(tool_name, block.get("input"), tasks, dependencies, warnings)
                    if tool_name == "Agent":
                        placeholder = self._subagent(tool_id, block.get("input"), span_by_tool.get(tool_id))
                        subagents.append(placeholder)
                        events.append(ExecutionEvent(ExecutionEventType.SUBAGENT, source_uuid, metadata={
                            "subagent": placeholder.subagent,
                            "tool_use_id": tool_id,
                            "agent_id": placeholder.agent_id,
                            "transcript_path": placeholder.transcript_path,
                            "span_id": placeholder.span_id,
                            "lazy": True,
                        }))
                loop = AgentLoop(
                    id=f"loop-{source_uuid or loop_index}", task_id=task_id,
                    model_input=tuple(history), assistant_content=tuple(blocks), events=tuple(events),
                    model=self._text(message.get("model")), stop_reason=self._text(message.get("stop_reason")),
                    usage=dict(message.get("usage") or {}), provenance=self._provenance(warnings),
                )
                loops.append(loop)
                tasks[task_id].loops.append(loop)
            elif role == "user":
                for block in blocks:
                    if not isinstance(block, Mapping) or block.get("type") != "tool_result":
                        continue
                    tool_id = self._text(block.get("tool_use_id"))
                    if not tool_id or tool_id not in pending:
                        warnings.append(f"unmatched_tool_result:{tool_id or 'missing'}")
                        continue
                    index = pending.pop(tool_id)
                    result = ExecutionEvent(ExecutionEventType.TOOL_RESULT, source_uuid, block.get("content"), tool_id, is_error=bool(block.get("is_error")))
                    loops[index] = replace(loops[index], events=(*loops[index].events, result), provenance=self._provenance(warnings))
                    self._replace_task_loop(tasks[loops[index].task_id], loops[index])
            history.append({"role": role, "content": blocks, "uuid": source_uuid, "parent_uuid": record.get("parentUuid")})

        warnings.extend(f"missing_tool_result:{tool_id}" for tool_id in pending)
        provenance = self._provenance(warnings)
        projected_tasks = tuple(
            ExecutionTask(t.id, t.subject, t.description, t.status, t.explicit, tuple(t.loops))
            for t in tasks.values() if t.explicit or t.loops
        )
        return ExecutionAgent(agent_id, projected_tasks, tuple(dependencies), tuple(subagents), provenance)

    @staticmethod
    def _content_blocks(content: Any, warnings: list[str]) -> list[Any]:
        if isinstance(content, str):
            return [{"type": "text", "text": content}]
        if isinstance(content, list):
            return list(content)
        warnings.append("unsupported_message_content")
        return []

    def _active_task(self, tasks: dict[str, _TaskState], warnings: list[str]) -> str:
        active = [task.id for task in tasks.values() if task.explicit and task.status == "in_progress"]
        if len(active) == 1:
            return active[0]
        if len(active) > 1:
            warnings.append("ambiguous_task_assignment")
        return self.IMPLICIT_TASK_ID

    def _apply_task_tool(self, name: str, value: Any, tasks: dict[str, _TaskState], dependencies: list[TaskDependency], warnings: list[str]) -> None:
        if not isinstance(value, Mapping):
            warnings.append(f"invalid_{name}_input")
            return
        task_id = self._text(value.get("taskId") or value.get("task_id") or value.get("id"))
        if name == "TaskCreate":
            task_id = task_id or f"task-{len(tasks)}"
            tasks[task_id] = _TaskState(task_id, self._text(value.get("subject")) or task_id, True, self._text(value.get("description")), self._text(value.get("status")) or "pending")
            for dependency in value.get("blockedBy") or value.get("blocked_by") or ():
                dependencies.append(TaskDependency(task_id, str(dependency)))
        elif task_id:
            task = tasks.setdefault(task_id, _TaskState(task_id, task_id, True))
            task.subject = self._text(value.get("subject")) or task.subject
            task.description = self._text(value.get("description")) or task.description
            task.status = self._text(value.get("status")) or task.status
            for dependency in value.get("addBlockedBy") or value.get("add_blocked_by") or ():
                dependencies.append(TaskDependency(task_id, str(dependency)))

    def _subagent(self, tool_id: str, value: Any, span: TraceSpan | None) -> SubagentPlaceholder:
        data = value if isinstance(value, Mapping) else {}
        metadata = span.metadata if span else {}
        return SubagentPlaceholder(
            tool_use_id=tool_id,
            subagent=self._text(metadata.get("subagent") or metadata.get("subagent_type") or data.get("subagent_type")),
            agent_id=(span.agent_id if span else None) or self._text(metadata.get("agent_id")),
            transcript_path=self._text(metadata.get("transcript_path") or metadata.get("agent_transcript_path")),
            span_id=span.id if span else None,
        )

    @staticmethod
    def _replace_task_loop(task: _TaskState, loop: AgentLoop) -> None:
        for index, current in enumerate(task.loops):
            if current.id == loop.id:
                task.loops[index] = loop
                return

    @staticmethod
    def _provenance(warnings: list[str]) -> ProjectionProvenance:
        unique = tuple(dict.fromkeys(warnings))
        completeness = ProjectionCompleteness.PARTIAL if unique else ProjectionCompleteness.COMPLETE
        return ProjectionProvenance(completeness=completeness, warnings=unique)

    @staticmethod
    def _text(value: Any) -> str | None:
        return value if isinstance(value, str) and value else None
