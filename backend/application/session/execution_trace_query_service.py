from __future__ import annotations

import json
import logging
from dataclasses import replace
from datetime import datetime, timedelta
from typing import Any

from domain.project.repository.project_repository import ProjectRepository
from domain.session.acl.transcript_reader import TranscriptReader
from domain.session.model.execution_trace import AgentLoop, ExecutionAgent, LoopDetailPage
from domain.session.repository.session_repository import SessionRepository
from domain.session.repository.trace_span_repository import TraceSpanRepository
from domain.session.service.execution_trace_projector import ExecutionTraceProjector
from domain.shared.business_exception import BusinessException

logger = logging.getLogger(__name__)


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
                records = self._read_all_records(project, session, transcript_path)
                records = self._filter_records_to_run(records, [agent_span])
            else:
                # Never fall back to the main session transcript: that makes a
                # subagent node render the main agent's steps. Persisted child
                # spans are the truthful fallback when the SDK did not provide
                # an agent transcript path.
                records = self._records_from_agent_spans(agent_span, projection_spans)
        else:
            records = self._read_all_records(project, session, None)
            records = self._filter_records_to_run(records, spans)

        agent = self._projector.project(records, projection_spans, agent_id)
        if agent_span is None and agent.request is None:
            request = self._request_for_run(session, spans)
            if request is not None:
                agent = replace(agent, request=request)
        return agent

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
    def _spans_owned_by_agent(agent_span: Any, spans: list[Any]) -> list[Any]:
        """Return direct work of one agent while preserving nested agent nodes."""
        by_id = {span.id: span for span in spans}
        owned: list[Any] = [agent_span]
        for candidate in spans:
            if candidate.id == agent_span.id:
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
            if nearest_agent_id == agent_span.id:
                owned.append(candidate)
        return owned

    @classmethod
    def _records_from_agent_spans(cls, agent_span: Any, spans: list[Any]) -> list[dict[str, Any]]:
        """Reconstruct only this subagent's turns from its persisted child spans."""
        turns = sorted(
            (span for span in spans if span.span_type == span.SPAN_TYPE_LLM_TURN),
            key=lambda span: span.started_time,
        )
        tools = sorted(
            (span for span in spans if span.span_type == span.SPAN_TYPE_TOOL_CALL),
            key=lambda span: span.started_time,
        )
        records: list[dict[str, Any]] = []
        if agent_span.input_preview:
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
                    tool.parent_span_id == agent_span.id
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
