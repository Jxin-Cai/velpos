from __future__ import annotations

import logging
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

        if agent_span_id:
            span = await self._trace_span_repository.find_by_id(agent_span_id)
            if span is None or span.session_id != session_id:
                raise BusinessException("agent span not found")
            transcript_path = span.metadata.get("transcript_path") or span.metadata.get("agent_transcript_path")
            agent_id = span.agent_id or agent_span_id

        records = self._read_all_records(project, session, transcript_path)

        spans = await self._trace_span_repository.find_by_run(session_id, run_id)

        return self._projector.project(records, spans, agent_id)

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
    def _find_loop(agent: ExecutionAgent, loop_id: str) -> AgentLoop | None:
        for task in agent.tasks:
            for loop in task.loops:
                if loop.id == loop_id:
                    return loop
        return None
