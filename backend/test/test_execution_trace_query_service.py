from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from application.session.execution_trace_query_service import ExecutionTraceQueryService
@pytest.mark.asyncio
async def test_returns_execution_tree_when_repositories_are_async() -> None:
    """The query service must await the async persistence adapters."""
    session = SimpleNamespace(project_id="project-1")
    project = SimpleNamespace(dir_path="/workspace")
    session_repository = Mock()
    session_repository.find_by_id = AsyncMock(return_value=session)
    project_repository = Mock()
    project_repository.find_by_id = AsyncMock(return_value=project)
    trace_repository = Mock()
    trace_repository.find_by_run = AsyncMock(return_value=[])
    transcript_reader = Mock()
    transcript_reader.read.return_value = SimpleNamespace(
        records=(), has_more=False, next_cursor=0
    )

    service = ExecutionTraceQueryService(
        session_repository=session_repository,
        project_repository=project_repository,
        trace_span_repository=trace_repository,
        transcript_reader=transcript_reader,
    )

    result = await service.get_execution_tree("session-1", "run-1")

    assert result.id == "main"
    session_repository.find_by_id.assert_awaited_once_with("session-1")
    project_repository.find_by_id.assert_awaited_once_with("project-1")
