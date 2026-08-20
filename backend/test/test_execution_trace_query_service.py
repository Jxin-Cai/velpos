from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from datetime import datetime, timedelta, timezone

import pytest

from application.session.execution_trace_query_service import ExecutionTraceQueryService, _tree_cache
from domain.session.acl.transcript_reader import TranscriptNotFoundError
from domain.session.model.trace_span import TraceSpan
from domain.session.service.execution_trace_projector import ExecutionTraceProjector
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


@pytest.mark.asyncio
async def test_rebuilds_cached_tree_when_run_version_changes() -> None:
    # Arrange
    _tree_cache.clear()
    trace_repository = Mock()
    trace_repository.find_run_version = AsyncMock(side_effect=["2:7:2", "2:7:3"])
    service = ExecutionTraceQueryService(
        session_repository=Mock(),
        project_repository=Mock(),
        trace_span_repository=trace_repository,
        transcript_reader=Mock(),
    )
    first_tree = SimpleNamespace(id="first")
    updated_tree = SimpleNamespace(id="updated")
    service.get_execution_tree = AsyncMock(side_effect=[first_tree, updated_tree])

    # Act
    await service.get_cached_execution_tree("session-1", "run-1")
    result = await service.get_cached_execution_tree("session-1", "run-1")

    # Assert
    assert result is updated_tree


@pytest.mark.asyncio
async def test_reuses_cached_tree_when_run_version_is_unchanged() -> None:
    # Arrange
    _tree_cache.clear()
    trace_repository = Mock()
    trace_repository.find_run_version = AsyncMock(side_effect=["3:9:3", "3:9:3"])
    service = ExecutionTraceQueryService(
        session_repository=Mock(),
        project_repository=Mock(),
        trace_span_repository=trace_repository,
        transcript_reader=Mock(),
    )
    tree = SimpleNamespace(id="stable")
    service.get_execution_tree = AsyncMock(return_value=tree)

    # Act
    await service.get_cached_execution_tree("session-1", "run-1")
    result = await service.get_cached_execution_tree("session-1", "run-1")

    # Assert
    assert result is tree
    service.get_execution_tree.assert_awaited_once()


@pytest.mark.asyncio
async def test_returns_terminal_failure_when_run_span_contains_error() -> None:
    # Arrange
    session = SimpleNamespace(
        project_id="project-1",
        model="claude-test",
        messages=[],
    )
    project = SimpleNamespace(dir_path="/workspace")
    run = TraceSpan.create(
        session_id="session-1",
        run_id="run-1",
        span_type=TraceSpan.SPAN_TYPE_RUN,
        name="Agent run",
    )
    run.fail(error="API Error: 503 NO_AVAILABLE_CHANNEL")
    transcript_reader = Mock()
    transcript_reader.read.return_value = SimpleNamespace(
        records=(
            {
                "type": "assistant",
                "uuid": "assistant-1",
                "message": {"role": "assistant", "content": "Upstream request failed"},
            },
        ),
        has_more=False,
        next_cursor=0,
    )
    service = ExecutionTraceQueryService(
        session_repository=Mock(find_by_id=AsyncMock(return_value=session)),
        project_repository=Mock(find_by_id=AsyncMock(return_value=project)),
        trace_span_repository=Mock(find_by_run=AsyncMock(return_value=[run])),
        transcript_reader=transcript_reader,
    )

    # Act
    result = await service.get_execution_tree("session-1", "run-1")

    # Assert
    assert result.error_message == "API Error: 503 NO_AVAILABLE_CHANNEL"
    assert result.tasks[0].loops[0].error_message == result.error_message


def test_filters_transcript_records_to_selected_run_window() -> None:
    start = datetime(2026, 7, 20, 1, 0, 0, tzinfo=timezone.utc)
    span = SimpleNamespace(started_time=start, ended_time=start.replace(minute=2))
    records = [
        {"timestamp": "2026-07-20T00:30:00Z", "uuid": "old"},
        {"timestamp": "2026-07-20T01:01:00Z", "uuid": "current"},
        {"uuid": "legacy-without-timestamp"},
    ]

    filtered = ExecutionTraceQueryService._filter_records_to_run(records, [span])

    assert [record["uuid"] for record in filtered] == ["current", "legacy-without-timestamp"]


def test_filters_records_when_trace_span_datetime_is_naive() -> None:
    start = datetime(2026, 7, 20, 1, 0, 0)
    span = SimpleNamespace(started_time=start, ended_time=start.replace(minute=2))
    records = [{"timestamp": "2026-07-20T01:01:00+08:00", "uuid": "current"}]

    filtered = ExecutionTraceQueryService._filter_records_to_run(records, [span])

    assert [record["uuid"] for record in filtered] == ["current"]


@pytest.mark.asyncio
async def test_reconstructs_subagent_from_owned_spans_when_transcript_path_is_missing() -> None:
    # Arrange
    session = SimpleNamespace(project_id="project-1")
    project = SimpleNamespace(dir_path="/workspace")
    subagent = TraceSpan.create(
        session_id="session-1",
        run_id="run-1",
        span_type=TraceSpan.SPAN_TYPE_SUBAGENT,
        name="researcher",
        agent_id="agent-1",
    )
    turn = TraceSpan.create(
        session_id="session-1",
        run_id="run-1",
        span_type=TraceSpan.SPAN_TYPE_LLM_TURN,
        name="subagent assistant",
        parent_span_id=subagent.id,
        agent_id="agent-1",
        input_preview="Inspect the repository",
        output_preview="I found the implementation",
    )
    tool = TraceSpan.create(
        session_id="session-1",
        run_id="run-1",
        span_type=TraceSpan.SPAN_TYPE_TOOL_CALL,
        name="Read",
        parent_span_id=subagent.id,
        agent_id="agent-1",
        tool_use_id="read-1",
        input_preview='{"file_path":"app.py"}',
    )
    tool.complete(output_preview="file contents")
    session_repository = Mock(find_by_id=AsyncMock(return_value=session))
    project_repository = Mock(find_by_id=AsyncMock(return_value=project))
    trace_repository = Mock(
        find_by_id=AsyncMock(return_value=subagent),
        find_by_run=AsyncMock(return_value=[subagent, turn, tool]),
    )
    transcript_reader = Mock()
    service = ExecutionTraceQueryService(
        session_repository=session_repository,
        project_repository=project_repository,
        trace_span_repository=trace_repository,
        transcript_reader=transcript_reader,
    )

    # Act
    result = await service.get_execution_tree("session-1", "run-1", subagent.id)

    # Assert
    transcript_reader.read.assert_not_called()
    assert result.id == "agent-1"
    assert result.tasks[0].loops[0].tool_names == ("Read",)


@pytest.mark.asyncio
async def test_reads_complete_subagent_transcript_when_official_result_contains_agent_id() -> None:
    # Arrange
    session = SimpleNamespace(project_id="project-1")
    project = SimpleNamespace(dir_path="/workspace")
    subagent = TraceSpan.create(
        session_id="session-1",
        run_id="run-1",
        span_type=TraceSpan.SPAN_TYPE_TOOL_CALL,
        name="Agent",
        tool_use_id="agent-tool",
        metadata={
            "telemetry.source": "claude_code_otel",
            "session.id": "claude-session-1",
            "new_context": '[TOOL RESULT: Agent]\n{"agentId":"child-1"}',
        },
    )
    transcript_reader = Mock()
    transcript_reader.read.return_value = SimpleNamespace(
        records=(
            {
                "type": "assistant",
                "uuid": "assistant-1",
                "message": {"role": "assistant", "content": [{
                    "type": "tool_use",
                    "id": "read-1",
                    "name": "Read",
                    "input": {"file_path": "app.py"},
                }]},
            },
            {
                "type": "user",
                "uuid": "result-1",
                "message": {"role": "user", "content": [{
                    "type": "tool_result",
                    "tool_use_id": "read-1",
                    "content": "file contents",
                }]},
            },
        ),
        has_more=False,
        next_cursor=0,
    )
    service = ExecutionTraceQueryService(
        session_repository=Mock(find_by_id=AsyncMock(return_value=session)),
        project_repository=Mock(find_by_id=AsyncMock(return_value=project)),
        trace_span_repository=Mock(
            find_by_id=AsyncMock(return_value=subagent),
            find_by_run=AsyncMock(return_value=[subagent]),
        ),
        transcript_reader=transcript_reader,
    )

    # Act
    result = await service.get_execution_tree("session-1", "run-1", subagent.id)

    # Assert
    assert result.tasks[0].loops[0].tool_names == ("Read",)


@pytest.mark.asyncio
async def test_reconstructs_main_execution_tree_when_transcript_file_is_missing() -> None:
    # Arrange
    session = SimpleNamespace(project_id="project-1", messages=[])
    project = SimpleNamespace(dir_path="/workspace")
    main_agent = TraceSpan.create(
        session_id="session-1",
        run_id="run-1",
        span_type=TraceSpan.SPAN_TYPE_AGENT,
        name="Main agent",
        agent_id="main",
        metadata={"role": "main"},
    )
    turn = TraceSpan.create(
        session_id="session-1",
        run_id="run-1",
        span_type=TraceSpan.SPAN_TYPE_LLM_TURN,
        name="main assistant",
        parent_span_id=main_agent.id,
        agent_id="main",
        input_preview="Inspect the failure",
        output_preview="The transcript was removed",
    )
    transcript_reader = Mock()
    transcript_reader.read.side_effect = TranscriptNotFoundError("transcript not found")
    service = ExecutionTraceQueryService(
        session_repository=Mock(find_by_id=AsyncMock(return_value=session)),
        project_repository=Mock(find_by_id=AsyncMock(return_value=project)),
        trace_span_repository=Mock(find_by_run=AsyncMock(return_value=[main_agent, turn])),
        transcript_reader=transcript_reader,
    )

    # Act
    result = await service.get_execution_tree("session-1", "run-1")

    # Assert
    assert result.tasks[0].loops[0].assistant_content == (
        {"type": "text", "text": "The transcript was removed"},
    )


@pytest.mark.asyncio
async def test_reconstructs_subagent_execution_tree_when_transcript_file_is_missing() -> None:
    # Arrange
    session = SimpleNamespace(project_id="project-1")
    project = SimpleNamespace(dir_path="/workspace")
    subagent = TraceSpan.create(
        session_id="session-1",
        run_id="run-1",
        span_type=TraceSpan.SPAN_TYPE_SUBAGENT,
        name="researcher",
        agent_id="agent-1",
        metadata={"transcript_path": "session/subagents/agent-1.jsonl"},
    )
    turn = TraceSpan.create(
        session_id="session-1",
        run_id="run-1",
        span_type=TraceSpan.SPAN_TYPE_LLM_TURN,
        name="subagent assistant",
        parent_span_id=subagent.id,
        agent_id="agent-1",
        output_preview="Recovered from spans",
    )
    transcript_reader = Mock()
    transcript_reader.read.side_effect = TranscriptNotFoundError("transcript not found")
    service = ExecutionTraceQueryService(
        session_repository=Mock(find_by_id=AsyncMock(return_value=session)),
        project_repository=Mock(find_by_id=AsyncMock(return_value=project)),
        trace_span_repository=Mock(
            find_by_id=AsyncMock(return_value=subagent),
            find_by_run=AsyncMock(return_value=[subagent, turn]),
        ),
        transcript_reader=transcript_reader,
    )

    # Act
    result = await service.get_execution_tree("session-1", "run-1", subagent.id)

    # Assert
    assert result.tasks[0].loops[0].assistant_content == (
        {"type": "text", "text": "Recovered from spans"},
    )


@pytest.mark.asyncio
async def test_resolves_tool_span_to_child_subagent_when_loading_execution_tree() -> None:
    # Arrange
    session = SimpleNamespace(project_id="project-1")
    project = SimpleNamespace(dir_path="/workspace")
    tool = TraceSpan.create(
        session_id="session-1",
        run_id="run-1",
        span_type=TraceSpan.SPAN_TYPE_TOOL_CALL,
        name="Agent",
        tool_use_id="agent-tool",
    )
    subagent = TraceSpan.create(
        session_id="session-1",
        run_id="run-1",
        span_type=TraceSpan.SPAN_TYPE_SUBAGENT,
        name="researcher",
        parent_span_id=tool.id,
        agent_id="agent-1",
        input_preview="Inspect the repository",
    )
    turn = TraceSpan.create(
        session_id="session-1",
        run_id="run-1",
        span_type=TraceSpan.SPAN_TYPE_LLM_TURN,
        name="subagent assistant",
        parent_span_id=subagent.id,
        agent_id="agent-1",
        output_preview="Inspection complete",
    )
    service = ExecutionTraceQueryService(
        session_repository=Mock(find_by_id=AsyncMock(return_value=session)),
        project_repository=Mock(find_by_id=AsyncMock(return_value=project)),
        trace_span_repository=Mock(
            find_by_id=AsyncMock(return_value=tool),
            find_by_run=AsyncMock(return_value=[tool, subagent, turn]),
        ),
        transcript_reader=Mock(),
    )

    # Act
    result = await service.get_execution_tree("session-1", "run-1", tool.id)

    # Assert
    assert result.id == "agent-1"
    assert result.tasks[0].loops[0].assistant_content == (
        {"type": "text", "text": "Inspection complete"},
    )


def test_returns_exact_source_message_when_run_has_message_id() -> None:
    # Arrange
    run = TraceSpan.create(
        session_id="session-1",
        run_id="run-1",
        span_type=TraceSpan.SPAN_TYPE_RUN,
        name="Agent run",
        metadata={"source_message_id": "message-current"},
    )
    session = SimpleNamespace(messages=[
        SimpleNamespace(content={"message_id": "message-old", "text": "Old request"}),
        SimpleNamespace(content={"message_id": "message-current", "text": "Current request"}),
    ])

    # Act
    request = ExecutionTraceQueryService._request_for_run(session, [run])

    # Assert
    assert request == "Current request"


def test_keeps_all_planned_tasks_for_current_run_while_excluding_other_messages() -> None:
    # Arrange
    start = datetime(2026, 7, 20, 9, 0, 0, tzinfo=timezone.utc)
    span = SimpleNamespace(started_time=start, ended_time=start.replace(minute=5))
    records = [
        {"timestamp": "2026-07-20T08:30:00Z", "type": "assistant", "uuid": "old-plan", "message": {"role": "assistant", "content": [{"type": "tool_use", "id": "old", "name": "TaskCreate", "input": {"taskId": "old", "subject": "Old message task"}}]}},
        {"timestamp": "2026-07-20T09:00:01Z", "type": "user", "uuid": "current-user", "message": {"role": "user", "content": "Current request"}},
        {"timestamp": "2026-07-20T09:00:02Z", "type": "assistant", "uuid": "current-plan", "message": {"role": "assistant", "content": [
            {"type": "tool_use", "id": "create-1", "name": "TaskCreate", "input": {"taskId": "1", "subject": "Inspect", "description": "Inspect current code"}},
            {"type": "tool_use", "id": "create-2", "name": "TaskCreate", "input": {"taskId": "2", "subject": "Implement", "description": "Implement the fix"}},
            {"type": "tool_use", "id": "create-3", "name": "TaskCreate", "input": {"taskId": "3", "subject": "Verify", "description": "Verify the result"}},
        ]}},
        {"timestamp": "2026-07-20T09:30:00Z", "type": "assistant", "uuid": "next-plan", "message": {"role": "assistant", "content": [{"type": "tool_use", "id": "next", "name": "TaskCreate", "input": {"taskId": "next", "subject": "Next message task"}}]}},
    ]

    # Act
    filtered = ExecutionTraceQueryService._filter_records_to_run(records, [span])
    projection = ExecutionTraceProjector().project(filtered)

    # Assert
    assert [task.subject for task in projection.tasks] == ["Inspect", "Implement", "Verify"]


@pytest.mark.asyncio
async def test_restores_plan_and_appends_steps_when_continuing_interrupted_run() -> None:
    # Arrange
    first_started = datetime(2026, 7, 20, 9, 0, 0, tzinfo=timezone.utc)
    continued_started = first_started.replace(minute=3)
    first_run = TraceSpan.create(
        session_id="session-1",
        run_id="run-1",
        span_type=TraceSpan.SPAN_TYPE_RUN,
        name="Agent run",
        metadata={"source_message_id": "message-1"},
    )
    first_run.started_time = first_started
    first_run.ended_time = first_started.replace(minute=2)
    first_run.status = TraceSpan.STATUS_CANCELLED
    continued_run = TraceSpan.create(
        session_id="session-1",
        run_id="run-2",
        span_type=TraceSpan.SPAN_TYPE_RUN,
        name="Agent run",
        metadata={"source_message_id": "message-2"},
    )
    continued_run.started_time = continued_started
    continued_run.ended_time = continued_started + timedelta(minutes=1)
    continued_run.status = TraceSpan.STATUS_COMPLETED
    session = SimpleNamespace(
        project_id="project-1",
        model="claude-sonnet",
        messages=[
            SimpleNamespace(content={"message_id": "message-1", "text": "Implement the feature"}),
            SimpleNamespace(content={"message_id": "message-2", "text": "继续"}),
        ],
    )
    records = [
        {
            "timestamp": "2026-07-20T09:00:00Z",
            "type": "user",
            "uuid": "user-1",
            "message": {"role": "user", "content": "Implement the feature"},
        },
        {
            "timestamp": "2026-07-20T09:00:01Z",
            "type": "assistant",
            "uuid": "plan",
            "message": {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "create-1",
                        "name": "TaskCreate",
                        "input": {
                            "taskId": "1",
                            "subject": "Inspect",
                            "description": "Inspect the current implementation",
                        },
                    },
                    {
                        "type": "tool_use",
                        "id": "create-2",
                        "name": "TaskCreate",
                        "input": {
                            "taskId": "2",
                            "subject": "Implement",
                            "description": "Implement the feature",
                            "blockedBy": ["1"],
                        },
                    },
                ],
            },
        },
        {
            "timestamp": "2026-07-20T09:00:02Z",
            "type": "assistant",
            "uuid": "start-task",
            "message": {
                "role": "assistant",
                "content": [{
                    "type": "tool_use",
                    "id": "update-1",
                    "name": "TaskUpdate",
                    "input": {"taskId": "1", "status": "completed"},
                }, {
                    "type": "tool_use",
                    "id": "update-2",
                    "name": "TaskUpdate",
                    "input": {"taskId": "2", "status": "in_progress"},
                }],
            },
        },
        {
            "timestamp": "2026-07-20T09:03:00Z",
            "type": "user",
            "uuid": "user-2",
            "message": {"role": "user", "content": "继续"},
        },
        {
            "timestamp": "2026-07-20T09:03:01Z",
            "type": "assistant",
            "uuid": "continued-step",
            "message": {
                "role": "assistant",
                "content": [{
                    "type": "tool_use",
                    "id": "bash-1",
                    "name": "Bash",
                    "input": {"command": "pytest"},
                }],
            },
        },
    ]
    transcript_reader = Mock()
    transcript_reader.read.return_value = SimpleNamespace(
        records=records,
        has_more=False,
        next_cursor=0,
    )
    trace_repository = Mock(
        find_by_run=AsyncMock(return_value=[continued_run]),
        find_by_session=AsyncMock(return_value=[first_run, continued_run]),
    )
    service = ExecutionTraceQueryService(
        session_repository=Mock(find_by_id=AsyncMock(return_value=session)),
        project_repository=Mock(
            find_by_id=AsyncMock(return_value=SimpleNamespace(dir_path="/workspace"))
        ),
        trace_span_repository=trace_repository,
        transcript_reader=transcript_reader,
    )

    # Act
    result = await service.get_execution_tree("session-1", "run-2")

    # Assert
    assert result.request == "继续"
    assert [task.subject for task in result.tasks] == ["Inspect", "Implement"]
    assert [(edge.task_id, edge.depends_on_task_id) for edge in result.dependencies] == [
        ("2", "1")
    ]
    assert result.tasks[1].loops[-1].id == "loop-continued-step"
    assert result.tasks[1].loops[-1].task_id == "2"
