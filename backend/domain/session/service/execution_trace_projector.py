from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from datetime import datetime
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
    _CREATED_TASK_ID_PATTERN = re.compile(r"\bTask\s+#?([A-Za-z0-9_-]+)\s+created\b", re.IGNORECASE)
    _SUBAGENT_TOOL_NAMES = frozenset({"Agent", "Task"})

    def project(
        self,
        records: Iterable[Mapping[str, Any]],
        spans: Iterable[TraceSpan] = (),
        agent_id: str = "main",
    ) -> ExecutionAgent:
        normalized_records = self._coalesce_assistant_turns(records)
        projection_spans = list(spans)
        span_by_tool = self._subagent_spans_by_tool(projection_spans)
        tasks = {self.IMPLICIT_TASK_ID: _TaskState(self.IMPLICIT_TASK_ID, "Direct execution", False, status="in_progress")}
        dependencies: list[TaskDependency] = []
        subagents: list[SubagentPlaceholder] = []
        loops: list[AgentLoop] = []
        pending: dict[str, int] = {}
        pending_task_creates: dict[str, str] = {}
        records_by_uuid: dict[str, dict[str, Any]] = {}
        latest_user_input: dict[str, Any] | None = None
        warnings: list[str] = []
        previous_timestamp: datetime | None = None
        request: Any = None

        for record in normalized_records:
            message = record.get("message")
            if not isinstance(message, Mapping):
                continue
            role = message.get("role") or record.get("type")
            blocks = self._content_blocks(message.get("content"), warnings)
            source_uuid = self._text(record.get("uuid"))
            record_timestamp = self._timestamp(record.get("timestamp"), warnings)
            if role == "assistant":
                turn_input = self._turn_input(record, records_by_uuid, latest_user_input)
                input_content = (turn_input,) if turn_input else ()
                input_timestamp = turn_input.get("timestamp") if turn_input else None
                task_id = self._task_for_blocks(blocks, tasks, warnings)
                has_explicit_tasks = any(task.explicit for task in tasks.values())
                events = [
                    ExecutionEvent(
                        ExecutionEventType.MODEL_INPUT,
                        source_uuid,
                        input_content,
                        timestamp=input_timestamp or previous_timestamp,
                    ),
                    ExecutionEvent(
                        ExecutionEventType.MODEL_OUTPUT,
                        source_uuid,
                        tuple(blocks),
                        timestamp=record_timestamp,
                    ),
                ]
                loop_index = len(loops)
                for block in blocks:
                    if not isinstance(block, Mapping) or block.get("type") != "tool_use":
                        if isinstance(block, Mapping) and block.get("type") == "thinking":
                            events.append(ExecutionEvent(
                                ExecutionEventType.THINKING,
                                source_uuid,
                                block.get("thinking") or block.get("text") or block,
                                metadata={"phase": "planning" if not has_explicit_tasks else "thinking"},
                                timestamp=record_timestamp,
                            ))
                        continue
                    tool_id = self._text(block.get("id"))
                    tool_name = self._text(block.get("name"))
                    if not tool_id:
                        warnings.append("tool_use_missing_id")
                        continue
                    events.append(ExecutionEvent(
                        ExecutionEventType.TOOL_USE,
                        source_uuid,
                        block.get("input"),
                        tool_id,
                        tool_name,
                        timestamp=record_timestamp,
                    ))
                    pending[tool_id] = loop_index
                    task_operation = self._task_operation(tool_name, block.get("input"))
                    if task_operation:
                        affected_task_id = self._apply_task_tool(
                            task_operation,
                            block.get("input"),
                            tasks,
                            dependencies,
                            warnings,
                            fallback_id=f"pending:{tool_id}",
                        )
                        if task_operation == "TaskCreate" and affected_task_id:
                            pending_task_creates[tool_id] = affected_task_id
                    if tool_name == "Agent" or (
                        tool_name in self._SUBAGENT_TOOL_NAMES
                        and task_operation is None
                        and self._is_subagent_input(block.get("input"))
                    ):
                        placeholder = self._subagent(tool_id, block.get("input"), span_by_tool.get(tool_id))
                        subagents.append(placeholder)
                        events.append(ExecutionEvent(
                            ExecutionEventType.SUBAGENT,
                            source_uuid,
                            content=block.get("input"),
                            metadata={
                                "subagent": placeholder.subagent,
                                "tool_use_id": tool_id,
                                "agent_id": placeholder.agent_id,
                                "transcript_path": placeholder.transcript_path,
                                "span_id": placeholder.span_id,
                                "lazy": True,
                            },
                            timestamp=record_timestamp,
                        ))
                # Keep the planning signal at the start of the assistant turn,
                # before the rendered model output and tool activity.
                thinking_events = [event for event in events if event.type == ExecutionEventType.THINKING]
                if thinking_events:
                    non_thinking_events = [event for event in events if event.type != ExecutionEventType.THINKING]
                    events = [non_thinking_events[0], *thinking_events, *non_thinking_events[1:]]
                started_time = input_timestamp or previous_timestamp or record_timestamp
                loop = AgentLoop(
                    id=f"loop-{source_uuid or loop_index}", task_id=task_id,
                    model_input=input_content, assistant_content=tuple(blocks), events=tuple(events),
                    model=self._text(message.get("model")), stop_reason=self._text(message.get("stop_reason")),
                    usage=dict(message.get("usage") or {}), provenance=self._provenance(warnings),
                    started_time=started_time,
                    ended_time=record_timestamp,
                    duration_ms=self._duration_ms(started_time, record_timestamp),
                    sequence=loop_index + 1,
                )
                loops.append(loop)
                tasks[task_id].loops.append(loop)
            elif role == "user":
                latest_user_input = {
                    "role": role,
                    "content": blocks,
                    "uuid": source_uuid,
                    "parent_uuid": record.get("parentUuid") or record.get("parent_uuid"),
                    "timestamp": record_timestamp,
                }
                if request is None and any(
                    not isinstance(block, Mapping) or block.get("type") != "tool_result"
                    for block in blocks
                ):
                    request = message.get("content")
                for block in blocks:
                    if not isinstance(block, Mapping) or block.get("type") != "tool_result":
                        continue
                    tool_id = self._text(block.get("tool_use_id"))
                    if not tool_id or tool_id not in pending:
                        warnings.append(f"unmatched_tool_result:{tool_id or 'missing'}")
                        continue
                    index = pending.pop(tool_id)
                    result = ExecutionEvent(
                        ExecutionEventType.TOOL_RESULT,
                        source_uuid,
                        block.get("content"),
                        tool_id,
                        is_error=bool(block.get("is_error")),
                        error_message=self._error_message(block.get("content")) if block.get("is_error") else None,
                        timestamp=record_timestamp,
                    )
                    ended_time = record_timestamp or loops[index].ended_time
                    loops[index] = replace(
                        loops[index],
                        events=(*loops[index].events, result),
                        provenance=self._provenance(warnings),
                        ended_time=ended_time,
                        duration_ms=self._duration_ms(loops[index].started_time, ended_time),
                        error_message=loops[index].error_message or result.error_message,
                    )
                    self._replace_task_loop(tasks[loops[index].task_id], loops[index])
                    provisional_task_id = pending_task_creates.pop(tool_id, None)
                    if provisional_task_id:
                        created_task_id = self._created_task_id(block.get("content"))
                        if created_task_id:
                            self._resolve_task_id(tasks, dependencies, provisional_task_id, created_task_id)
                        else:
                            warnings.append(f"task_create_result_missing_id:{tool_id}")
            if source_uuid:
                indexed_record = {
                    "role": role,
                    "content": blocks,
                    "uuid": source_uuid,
                    "parent_uuid": record.get("parentUuid") or record.get("parent_uuid"),
                    "timestamp": record_timestamp,
                }
                for record_uuid in record.get("_source_uuids") or (source_uuid,):
                    if isinstance(record_uuid, str) and record_uuid:
                        records_by_uuid[record_uuid] = indexed_record
            previous_timestamp = record_timestamp or previous_timestamp

        warnings.extend(f"missing_tool_result:{tool_id}" for tool_id in pending)
        provenance = self._provenance(warnings)
        visible_tasks = [task for task in tasks.values() if task.explicit]
        implicit_task = tasks[self.IMPLICIT_TASK_ID]
        if visible_tasks and implicit_task.loops:
            self._assign_unowned_loops(implicit_task.loops, visible_tasks, loops)
        if not visible_tasks:
            visible_tasks = [task for task in tasks.values() if task.loops]
        projected_tasks = tuple(
            ExecutionTask(t.id, t.subject, t.description, t.status, t.explicit, tuple(t.loops))
            for t in visible_tasks
        )
        return ExecutionAgent(agent_id, projected_tasks, tuple(dependencies), tuple(subagents), provenance, request)

    @staticmethod
    def _subagent_spans_by_tool(spans: list[TraceSpan]) -> dict[str, TraceSpan]:
        """Index only real subagent spans by their invoking tool call ID."""
        by_id = {span.id: span for span in spans}
        result: dict[str, TraceSpan] = {}
        for span in spans:
            if span.span_type != TraceSpan.SPAN_TYPE_SUBAGENT:
                continue
            if span.tool_use_id:
                result[span.tool_use_id] = span
            parent = by_id.get(span.parent_span_id or "")
            if parent and parent.span_type == TraceSpan.SPAN_TYPE_TOOL_CALL and parent.tool_use_id:
                result[parent.tool_use_id] = span
        return result

    @classmethod
    def _coalesce_assistant_turns(
        cls,
        records: Iterable[Mapping[str, Any]],
    ) -> list[dict[str, Any]]:
        """Merge transcript fragments that belong to one assistant turn.

        Claude JSONL commonly persists thinking, text, and tool-use blocks as
        separate assistant records.  Their parent UUIDs form one uninterrupted
        chain.  Treating each fragment as a model call duplicates the input and
        loses the actual agent-loop boundary.
        """
        normalized: list[dict[str, Any]] = []
        for source in records:
            record = dict(source)
            message = record.get("message")
            role = message.get("role") if isinstance(message, Mapping) else record.get("type")
            previous = normalized[-1] if normalized else None
            previous_message = previous.get("message") if previous else None
            previous_role = (
                previous_message.get("role")
                if isinstance(previous_message, Mapping)
                else (previous.get("type") if previous else None)
            )
            parent_uuid = record.get("parentUuid") or record.get("parent_uuid")
            previous_tail_uuid = previous.get("_tail_uuid") if previous else None
            if (
                role == "assistant"
                and previous_role == "assistant"
                and isinstance(parent_uuid, str)
                and parent_uuid == previous_tail_uuid
                and isinstance(message, Mapping)
                and isinstance(previous_message, Mapping)
            ):
                merged_message = dict(previous_message)
                merged_message["content"] = [
                    *cls._raw_content_blocks(previous_message.get("content")),
                    *cls._raw_content_blocks(message.get("content")),
                ]
                for key in ("model", "stop_reason", "usage"):
                    if message.get(key) is not None:
                        merged_message[key] = message.get(key)
                previous["message"] = merged_message
                previous["timestamp"] = record.get("timestamp") or previous.get("timestamp")
                previous["_tail_uuid"] = record.get("uuid") or previous_tail_uuid
                previous.setdefault("_source_uuids", []).append(record.get("uuid"))
                continue
            record["_tail_uuid"] = record.get("uuid")
            record["_source_uuids"] = [record.get("uuid")]
            normalized.append(record)
        return normalized

    @staticmethod
    def _raw_content_blocks(content: Any) -> list[Any]:
        if isinstance(content, list):
            return list(content)
        if isinstance(content, str):
            return [{"type": "text", "text": content}]
        return []

    @staticmethod
    def _turn_input(
        record: Mapping[str, Any],
        records_by_uuid: Mapping[str, dict[str, Any]],
        latest_user_input: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        """Resolve the input delta for one model turn, not its cumulative history."""
        parent_uuid = record.get("parentUuid") or record.get("parent_uuid")
        parent = records_by_uuid.get(parent_uuid) if isinstance(parent_uuid, str) else None
        if parent and parent.get("role") == "user":
            return parent
        return latest_user_input

    @staticmethod
    def _assign_unowned_loops(
        unowned_loops: list[AgentLoop],
        explicit_tasks: list[_TaskState],
        all_loops: list[AgentLoop],
    ) -> None:
        """Keep coordination and final-response turns in the visible call chain.

        Task tools do not identify an owner for planning turns or for the final
        answer after every task has completed.  Attach those turns to the
        nearest explicit task instead of silently dropping them.
        """
        order = {loop.id: index for index, loop in enumerate(all_loops)}
        owned = [
            (order.get(loop.id, 0), task)
            for task in explicit_tasks
            for loop in task.loops
        ]
        for loop in unowned_loops:
            loop_index = order.get(loop.id, 0)
            if owned:
                _, target = min(
                    owned,
                    key=lambda item: (abs(item[0] - loop_index), item[0] > loop_index),
                )
            else:
                target = explicit_tasks[0]
            if loop.id not in {item.id for item in target.loops}:
                target.loops.append(replace(loop, task_id=target.id))
        for task in explicit_tasks:
            task.loops.sort(key=lambda loop: order.get(loop.id, 0))

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

    def _task_for_blocks(
        self,
        blocks: Iterable[Any],
        tasks: dict[str, _TaskState],
        warnings: list[str],
    ) -> str:
        updated_task_ids: list[str] = []
        for block in blocks:
            if not isinstance(block, Mapping) or block.get("type") != "tool_use":
                continue
            if self._task_operation(self._text(block.get("name")), block.get("input")) != "TaskUpdate":
                continue
            value = block.get("input")
            if not isinstance(value, Mapping):
                continue
            task_id = self._text(value.get("taskId") or value.get("task_id") or value.get("id"))
            if task_id and task_id in tasks:
                updated_task_ids.append(task_id)
        unique_task_ids = tuple(dict.fromkeys(updated_task_ids))
        if len(unique_task_ids) == 1:
            return unique_task_ids[0]
        if len(unique_task_ids) > 1:
            warnings.append("ambiguous_task_update_assignment")
        return self._active_task(tasks, warnings)

    def _apply_task_tool(
        self,
        name: str,
        value: Any,
        tasks: dict[str, _TaskState],
        dependencies: list[TaskDependency],
        warnings: list[str],
        fallback_id: str,
    ) -> str | None:
        if not isinstance(value, Mapping):
            warnings.append(f"invalid_{name}_input")
            return None
        task_id = self._text(value.get("taskId") or value.get("task_id") or value.get("id"))
        if name == "TaskCreate":
            task_id = task_id or fallback_id
            task = tasks.get(task_id)
            if task is None:
                task = _TaskState(task_id, self._text(value.get("subject")) or task_id, True)
                tasks[task_id] = task
            task.subject = self._text(value.get("subject")) or task.subject
            task.description = self._text(value.get("description")) or task.description
            task.status = self._text(value.get("status")) or task.status
            for dependency in value.get("blockedBy") or value.get("blocked_by") or ():
                dependencies.append(TaskDependency(task_id, str(dependency)))
        elif task_id:
            task = tasks.get(task_id)
            if task is None:
                warnings.append(f"unknown_task_update:{task_id}")
                return None
            task.subject = self._text(value.get("subject")) or task.subject
            task.description = self._text(value.get("description")) or task.description
            task.status = self._text(value.get("status")) or task.status
            for dependency in value.get("addBlockedBy") or value.get("add_blocked_by") or ():
                dependencies.append(TaskDependency(task_id, str(dependency)))
        return task_id

    def _created_task_id(self, content: Any) -> str | None:
        if isinstance(content, str):
            match = self._CREATED_TASK_ID_PATTERN.search(content)
            return match.group(1) if match else None
        if isinstance(content, Mapping):
            direct_id = self._text(content.get("taskId") or content.get("task_id") or content.get("id"))
            return direct_id or self._created_task_id(content.get("text") or content.get("content"))
        if isinstance(content, (list, tuple)):
            for item in content:
                task_id = self._created_task_id(item)
                if task_id:
                    return task_id
        return None

    @staticmethod
    def _resolve_task_id(
        tasks: dict[str, _TaskState],
        dependencies: list[TaskDependency],
        provisional_id: str,
        resolved_id: str,
    ) -> None:
        if provisional_id == resolved_id or provisional_id not in tasks:
            return
        task = tasks.pop(provisional_id)
        existing = tasks.get(resolved_id)
        if existing is None:
            task.id = resolved_id
            tasks[resolved_id] = task
        else:
            existing.subject = task.subject or existing.subject
            existing.description = task.description or existing.description
            existing.explicit = True
            existing.loops.extend(loop for loop in task.loops if loop.id not in {item.id for item in existing.loops})
        for index, dependency in enumerate(dependencies):
            task_id = resolved_id if dependency.task_id == provisional_id else dependency.task_id
            depends_on = resolved_id if dependency.depends_on_task_id == provisional_id else dependency.depends_on_task_id
            dependencies[index] = TaskDependency(task_id, depends_on)

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
    def _is_subagent_input(value: Any) -> bool:
        if not isinstance(value, Mapping):
            return False
        # The Task tool is overloaded by Claude integrations. Task-manager
        # payloads must never be mistaken for a subagent invocation.
        if any(value.get(key) is not None for key in ("subject", "activeForm", "taskId", "task_id", "blockedBy", "blocked_by", "status")):
            return False
        return any(
            value.get(key) is not None
            for key in ("subagent_type", "agent_type", "prompt", "subagent_prompt", "agent_prompt")
        )

    @staticmethod
    def _task_operation(tool_name: str | None, value: Any) -> str | None:
        if tool_name in {"TaskCreate", "TaskUpdate"}:
            return tool_name
        if tool_name != "Task" or not isinstance(value, Mapping):
            return None
        has_task_id = value.get("taskId") is not None or value.get("task_id") is not None
        has_subject = value.get("subject") is not None or value.get("activeForm") is not None
        if has_subject and not has_task_id:
            return "TaskCreate"
        if has_task_id and any(value.get(key) is not None for key in ("status", "subject", "description", "activeForm", "addBlockedBy", "add_blocked_by")):
            return "TaskUpdate"
        return None

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

    @classmethod
    def _error_message(cls, value: Any) -> str | None:
        if isinstance(value, str):
            return cls._truncate_error_message(value)
        if isinstance(value, Mapping):
            for key in ("error", "error_message", "message", "stderr", "text", "detail"):
                message = cls._error_message(value.get(key))
                if message:
                    return message
            return None
        if isinstance(value, list):
            for item in value:
                message = cls._error_message(item)
                if message:
                    return message
        return None

    @staticmethod
    def _truncate_error_message(message: str) -> str | None:
        normalized = message.strip()
        if not normalized:
            return None
        max_length = 2_000
        return normalized if len(normalized) <= max_length else f"{normalized[:max_length - 3]}..."

    @staticmethod
    def _timestamp(value: Any, warnings: list[str]) -> datetime | None:
        if not isinstance(value, str) or not value:
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            warnings.append("invalid_record_timestamp")
            return None

    @staticmethod
    def _duration_ms(started_time: datetime | None, ended_time: datetime | None) -> int:
        if started_time is None or ended_time is None or ended_time < started_time:
            return 0
        return max(int((ended_time - started_time).total_seconds() * 1000), 0)
