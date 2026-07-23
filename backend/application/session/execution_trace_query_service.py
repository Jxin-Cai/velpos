from __future__ import annotations

import json
import logging
import re
from dataclasses import replace
from datetime import datetime, timedelta
from typing import Any

from domain.project.repository.project_repository import ProjectRepository
from domain.session.acl.transcript_reader import TranscriptNotFoundError, TranscriptReader
from domain.session.model.execution_trace import AgentLoop, ExecutionAgent, LoopDetailPage
from domain.session.repository.session_repository import SessionRepository
from domain.session.repository.trace_span_repository import TraceSpanRepository
from domain.session.service.execution_trace_projector import ExecutionTraceProjector
from domain.shared.business_exception import BusinessException

logger = logging.getLogger(__name__)

_CONTINUATION_REQUEST_PATTERN = re.compile(
    r"^\s*(?:"
    r"继续(?:执行|处理|完成|往下|上次的任务|刚才的任务)?"
    r"|接着(?:执行|处理|完成|做|来)?"
    r"|从(?:刚才|上次)?中断处继续"
    r"|continue(?:\s+(?:where\s+you\s+left\s+off|the\s+(?:task|plan)))?"
    r"|resume(?:\s+(?:the\s+)?(?:task|plan|execution))?"
    r")\s*[。.!！]?\s*$",
    re.IGNORECASE,
)


class ExecutionTraceQueryService:
    """Thin orchestration layer for execution trace queries.

    Coordinates the TranscriptReader, TraceSpanRepository, and
    ExecutionTraceProjector to produce projected execution trees and
    loop detail pages.
    """

    def __init__(
        self,
        session_repository: SessionRepository,
        project_repository: ProjectRepository,
        trace_span_repository: TraceSpanRepository,
        transcript_reader: TranscriptReader,
        projector: ExecutionTraceProjector | None = None,
    ) -> None:
        self._session_repository = session_repository
        self._project_repository = project_repository
        self._trace_span_repository = trace_span_repository
        self._transcript_reader = transcript_reader
        self._projector = projector or ExecutionTraceProjector()

    async def get_execution_tree(
        self,
        session_id: str,
        run_id: str,
        agent_span_id: str | None = None,
    ) -> ExecutionAgent:
        """Project the full execution tree for a run (or a subagent span)."""
        session = await self._session_repository.find_by_id(session_id)
        if session is None:
            raise BusinessException("session not found")

        project = await self._project_repository.find_by_id(session.project_id)
        if project is None:
            raise BusinessException("project not found")

        transcript_path: str | None = None
        agent_id = "main"
        spans = await self._trace_span_repository.find_by_run(session_id, run_id)

        agent_span = None
        if agent_span_id:
            span = await self._trace_span_repository.find_by_id(agent_span_id)
            if span is None or span.session_id != session_id or span.run_id != run_id:
                raise BusinessException("agent span not found")
            if span.span_type != span.SPAN_TYPE_SUBAGENT:
                span = self._resolve_subagent_span(span, spans)
                if span is None:
                    raise BusinessException("agent span is not a subagent")
            agent_span = span
            transcript_path = span.metadata.get("transcript_path") or span.metadata.get("agent_transcript_path")
            agent_id = span.agent_id or agent_span_id

        projection_spans = spans
        if agent_span is not None:
            projection_spans = self._spans_owned_by_agent(agent_span, spans)
            if transcript_path:
                try:
                    records = self._read_all_records(project, session, transcript_path)
                    records = self._filter_records_to_run(records, [agent_span])
                except TranscriptNotFoundError:
                    logger.warning(
                        "subagent transcript not found; reconstructing execution tree from spans",
                        extra={"session_id": session_id, "run_id": run_id, "agent_id": agent_id},
                    )
                    records = self._records_from_agent_spans(agent_span, projection_spans)
            else:
                # Never fall back to the main session transcript: that makes a
                # subagent node render the main agent's steps. Persisted child
                # spans are the truthful fallback when the SDK did not provide
                # an agent transcript path.
                records = self._records_from_agent_spans(agent_span, projection_spans)
        else:
            try:
                all_records = self._read_all_records(project, session, None)
                records = self._filter_records_to_run(all_records, spans)
                continuation_spans = await self._continuation_spans(
                    session_id,
                    run_id,
                    session,
                    spans,
                )
                if (
                    len(continuation_spans) > len(spans)
                    and not self._contains_task_create(records)
                ):
                    continuation_records = self._filter_records_to_run(
                        all_records,
                        continuation_spans,
                    )
                    if self._contains_task_create(continuation_records):
                        records = continuation_records
                        projection_spans = continuation_spans
            except TranscriptNotFoundError:
                logger.warning(
                    "session transcript not found; reconstructing execution tree from spans",
                    extra={"session_id": session_id, "run_id": run_id},
                )
                main_agent_span = next((
                    span for span in spans
                    if span.span_type == span.SPAN_TYPE_AGENT
                    and span.metadata.get("role") == "main"
                ), None)
                main_spans = self._spans_owned_by_agent(main_agent_span, spans)
                records = self._records_from_agent_spans(main_agent_span, main_spans)

        default_model = (
            agent_span.metadata.get("model")
            if agent_span is not None
            else getattr(session, "model", None)
        )
        agent = self._projector.project(
            records,
            projection_spans,
            agent_id,
            default_model=default_model,
        )
        if agent_span is None:
            request = self._request_for_run(session, spans)
            if request is not None:
                agent = replace(agent, request=request)
        return agent

    async def _continuation_spans(
        self,
        session_id: str,
        run_id: str,
        session: Any,
        current_spans: list[Any],
    ) -> list[Any]:
        """Return adjacent interrupted runs that the selected run continues.

        A resumed SDK conversation still creates a new Velpos run. The
        transcript therefore retains the task state, while a run-only time
        slice loses the TaskCreate records that define its plan. Link only an
        explicit continuation request to the immediately preceding interrupted
        run so unrelated messages remain isolated.
        """
        request = self._request_for_run(session, current_spans)
        if not self._is_continuation_request(request):
            return current_spans

        session_spans = await self._trace_span_repository.find_by_session(session_id)
        run_spans = sorted(
            (
                span
                for span in session_spans
                if span.span_type == span.SPAN_TYPE_RUN
            ),
            key=lambda span: span.started_time,
        )
        current_index = next(
            (index for index, span in enumerate(run_spans) if span.run_id == run_id),
            None,
        )
        if current_index is None:
            return current_spans

        included_run_ids = {run_id}
        cursor = current_index
        while cursor > 0:
            child = run_spans[cursor]
            child_spans = [
                span for span in session_spans if span.run_id == child.run_id
            ]
            if not self._is_continuation_request(
                self._request_for_run(session, child_spans)
            ):
                break
            previous = run_spans[cursor - 1]
            if previous.status not in {
                previous.STATUS_CANCELLED,
                previous.STATUS_ABANDONED,
            }:
                break
            included_run_ids.add(previous.run_id)
            cursor -= 1

        if len(included_run_ids) == 1:
            return current_spans
        return [
            span for span in session_spans if span.run_id in included_run_ids
        ]

    @staticmethod
    def _is_continuation_request(request: Any) -> bool:
        if not isinstance(request, str):
            return False
        return _CONTINUATION_REQUEST_PATTERN.fullmatch(request) is not None

    @staticmethod
    def _contains_task_create(records: list[dict[str, Any]]) -> bool:
        for record in records:
            message = record.get("message")
            if not isinstance(message, dict):
                continue
            content = message.get("content")
            blocks = content if isinstance(content, list) else ()
            for block in blocks:
                if not isinstance(block, dict) or block.get("type") != "tool_use":
                    continue
                name = block.get("name")
                value = block.get("input")
                if name == "TaskCreate":
                    return True
                if (
                    name == "Task"
                    and isinstance(value, dict)
                    and (value.get("subject") is not None or value.get("activeForm") is not None)
                    and value.get("taskId") is None
                    and value.get("task_id") is None
                ):
                    return True
        return False

    @staticmethod
    def _resolve_subagent_span(span: Any, spans: list[Any]) -> Any | None:
        """Resolve a legacy tool-call ID to the subagent span it invoked."""
        direct_child = next((
            candidate for candidate in spans
            if candidate.span_type == candidate.SPAN_TYPE_SUBAGENT
            and candidate.parent_span_id == span.id
        ), None)
        if direct_child is not None:
            return direct_child
        if not span.tool_use_id:
            return None
        return next((
            candidate for candidate in spans
            if candidate.span_type == candidate.SPAN_TYPE_SUBAGENT
            and candidate.tool_use_id == span.tool_use_id
        ), None)

    async def get_loop_detail(
        self,
        session_id: str,
        run_id: str,
        loop_id: str,
        agent_span_id: str | None = None,
        cursor: int = 0,
        limit: int = 100,
    ) -> LoopDetailPage:
        """Return a paginated detail page for a specific loop within a run."""
        agent = await self.get_execution_tree(session_id, run_id, agent_span_id)
        loop = self._find_loop(agent, loop_id)
        if loop is None:
            raise BusinessException("loop not found")
        return loop.detail_page(cursor, limit)

    def _read_all_records(
        self,
        project: Any,
        session: Any,
        transcript_path: str | None,
    ) -> list[dict[str, Any]]:
        """Read all transcript records by paginating through the reader."""
        all_records: list[dict[str, Any]] = []
        page_cursor = 0
        while True:
            page = self._transcript_reader.read(
                project,
                session,
                transcript_path=transcript_path,
                cursor=page_cursor,
                limit=500,
            )
            all_records.extend(page.records)
            if not page.has_more:
                break
            page_cursor = page.next_cursor
        return all_records

    @staticmethod
    def _spans_owned_by_agent(agent_span: Any | None, spans: list[Any]) -> list[Any]:
        """Return direct work of one agent while preserving nested agent nodes."""
        by_id = {span.id: span for span in spans}
        owned: list[Any] = [agent_span] if agent_span is not None else []
        owner_id = (
            agent_span.id
            if agent_span is not None and agent_span.span_type == agent_span.SPAN_TYPE_SUBAGENT
            else None
        )
        for candidate in spans:
            if agent_span is not None and candidate.id == agent_span.id:
                continue
            parent_id = candidate.parent_span_id
            nearest_agent_id = None
            visited: set[str] = set()
            while parent_id and parent_id not in visited:
                visited.add(parent_id)
                parent = by_id.get(parent_id)
                if parent is None:
                    break
                if parent.span_type == parent.SPAN_TYPE_SUBAGENT:
                    nearest_agent_id = parent.id
                    break
                parent_id = parent.parent_span_id
            if nearest_agent_id == owner_id:
                owned.append(candidate)
        return owned

    @classmethod
    def _records_from_agent_spans(
        cls,
        agent_span: Any | None,
        spans: list[Any],
    ) -> list[dict[str, Any]]:
        """Reconstruct one agent's turns from its persisted spans."""
        turns = sorted(
            (span for span in spans if span.span_type == span.SPAN_TYPE_LLM_TURN),
            key=lambda span: span.started_time,
        )
        tools = sorted(
            (span for span in spans if span.span_type == span.SPAN_TYPE_TOOL_CALL),
            key=lambda span: span.started_time,
        )
        records: list[dict[str, Any]] = []
        if agent_span is not None and agent_span.input_preview:
            records.append({
                "type": "user",
                "uuid": f"{agent_span.id}-request",
                "timestamp": agent_span.started_time.isoformat(),
                "message": {"role": "user", "content": cls._preview_payload(agent_span.input_preview)},
            })
        for index, turn in enumerate(turns):
            next_started = turns[index + 1].started_time if index + 1 < len(turns) else None
            turn_tools = [tool for tool in tools if (
                tool.parent_span_id == turn.id
                or (
                    agent_span is not None
                    and tool.parent_span_id == agent_span.id
                    and tool.started_time >= turn.started_time
                    and (next_started is None or tool.started_time < next_started)
                )
            )]
            if turn.input_preview:
                records.append({
                    "type": "user",
                    "uuid": f"{turn.id}-input",
                    "timestamp": turn.started_time.isoformat(),
                    "message": {"role": "user", "content": cls._preview_payload(turn.input_preview)},
                })
            blocks: list[dict[str, Any]] = []
            thinking = turn.metadata.get("thinking_preview")
            if thinking:
                blocks.append({"type": "thinking", "thinking": thinking})
            if turn.output_preview:
                blocks.append({"type": "text", "text": turn.output_preview})
            for tool in turn_tools:
                blocks.append({
                    "type": "tool_use",
                    "id": tool.tool_use_id or tool.id,
                    "name": tool.name,
                    "input": cls._preview_payload(tool.input_preview),
                })
            records.append({
                "type": "assistant",
                "uuid": turn.id,
                "timestamp": (turn.ended_time or turn.started_time).isoformat(),
                "message": {
                    "role": "assistant",
                    "model": turn.metadata.get("model"),
                    "content": blocks,
                },
            })
            results = [{
                "type": "tool_result",
                "tool_use_id": tool.tool_use_id or tool.id,
                "content": cls._preview_payload(tool.output_preview),
                "is_error": tool.status == tool.STATUS_FAILED,
            } for tool in turn_tools if tool.output_preview is not None]
            if results:
                records.append({
                    "type": "user",
                    "uuid": f"{turn.id}-results",
                    "timestamp": max(
                        (tool.ended_time or tool.started_time for tool in turn_tools),
                        default=turn.ended_time or turn.started_time,
                    ).isoformat(),
                    "message": {"role": "user", "content": results},
                })
        return records

    @staticmethod
    def _request_for_run(session: Any, spans: list[Any]) -> Any:
        run_span = next((span for span in spans if span.span_type == span.SPAN_TYPE_RUN), None)
        source_message_id = run_span.metadata.get("source_message_id") if run_span else None
        if not source_message_id:
            return None
        for message in getattr(session, "messages", ()):
            content = getattr(message, "content", None)
            if isinstance(content, dict) and content.get("message_id") == source_message_id:
                return content.get("text") or content
        return None

    @staticmethod
    def _preview_payload(value: Any) -> Any:
        if not isinstance(value, str):
            return value
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value

    @staticmethod
    def _filter_records_to_run(records: list[dict[str, Any]], spans: list[Any]) -> list[dict[str, Any]]:
        """Keep only transcript records belonging to the selected trace run.

        Claude's JSONL transcript is session-scoped and does not carry Velpos's
        run id. Trace span timestamps are the reliable boundary between user
        turns; records without timestamps are retained for backwards
        compatibility with older imported transcripts.

        Records that belong to subagent conversations (identified by
        parent_tool_use_id) are excluded so that the main agent projection
        does not duplicate subagent activity as top-level loops.
        """
        timestamps = [
            span.started_time
            for span in spans
            if getattr(span, "started_time", None) is not None
        ]
        ended = [
            span.ended_time
            for span in spans
            if getattr(span, "ended_time", None) is not None
        ]
        if not timestamps:
            return records
        started = min(timestamps) - timedelta(seconds=2)
        finished = max(ended or timestamps) + timedelta(seconds=2)
        boundary_tz = started.tzinfo

        filtered: list[dict[str, Any]] = []
        for record in records:
            if record.get("parent_tool_use_id") or record.get("parentToolUseId"):
                continue
            raw_timestamp = record.get("timestamp")
            if not isinstance(raw_timestamp, str) or not raw_timestamp:
                filtered.append(record)
                continue
            try:
                timestamp = datetime.fromisoformat(raw_timestamp.replace("Z", "+00:00"))
            except ValueError:
                filtered.append(record)
                continue
            # TraceSpan is persisted by SQLAlchemy as a naive local datetime,
            # while transcript timestamps are commonly offset-aware. Normalize
            # the record to the span's representation before comparing; without
            # this, opening a trace raises ``can't compare offset-naive and
            # offset-aware datetimes``.
            if boundary_tz is None:
                if timestamp.tzinfo is not None:
                    timestamp = timestamp.astimezone().replace(tzinfo=None)
            elif timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=boundary_tz)
            if started <= timestamp <= finished:
                filtered.append(record)
        return filtered

    @staticmethod
    def _find_loop(agent: ExecutionAgent, loop_id: str) -> AgentLoop | None:
        for task in agent.tasks:
            for loop in task.loops:
                if loop.id == loop_id:
                    return loop
        return None
