from domain.session.model.execution_trace import (
    ExecutionEventType,
    ProjectionCompleteness,
)
from domain.session.model.trace_span import TraceSpan
from domain.session.service.execution_trace_projector import ExecutionTraceProjector


def test_creates_implicit_task_and_loop_when_transcript_has_no_explicit_task() -> None:
    # Arrange
    records = [
        {"type": "user", "uuid": "user-1", "message": {"role": "user", "content": "Implement it"}},
        {
            "type": "assistant",
            "uuid": "assistant-1",
            "message": {
                "role": "assistant",
                "model": "claude-test",
                "content": [{"type": "text", "text": "Done"}],
            },
        },
    ]

    # Act
    projection = ExecutionTraceProjector().project(records)

    # Assert
    assert projection.tasks[0].id == ExecutionTraceProjector.IMPLICIT_TASK_ID
    assert projection.tasks[0].explicit is False
    assert projection.tasks[0].loops[0].assistant_content == ({"type": "text", "text": "Done"},)
    assert projection.tasks[0].loops[0].model_input[0]["content"] == [{"type": "text", "text": "Implement it"}]
    assert projection.tasks[0].loops[0].provenance.reconstructed_from_transcript is True


def test_projects_thinking_block_as_planning_event_before_explicit_tasks() -> None:
    # Arrange
    records = [{
        "type": "assistant",
        "uuid": "assistant-plan",
        "message": {
            "role": "assistant",
            "content": [{"type": "thinking", "thinking": "Break the request into tasks first."}],
        },
    }]

    # Act
    loop = ExecutionTraceProjector().project(records).tasks[0].loops[0]

    # Assert
    planning = [event for event in loop.events if event.type == ExecutionEventType.THINKING]
    assert len(planning) == 1
    assert planning[0].metadata["phase"] == "planning"


def test_attaches_pre_execution_planning_to_first_explicit_task() -> None:
    # Arrange
    records = [
        {
            "type": "assistant",
            "uuid": "assistant-plan",
            "message": {
                "role": "assistant",
                "content": [
                    {"type": "thinking", "thinking": "Inspect first, then implement."},
                    {
                        "type": "tool_use",
                        "id": "create-1",
                        "name": "TaskCreate",
                        "input": {"taskId": "task-1", "subject": "Implement trace"},
                    },
                ],
            },
        },
        {
            "type": "assistant",
            "uuid": "assistant-work",
            "message": {
                "role": "assistant",
                "content": [{
                    "type": "tool_use",
                    "id": "update-1",
                    "name": "TaskUpdate",
                    "input": {"taskId": "task-1", "status": "in_progress"},
                }],
            },
        },
    ]

    # Act
    task = ExecutionTraceProjector().project(records).tasks[0]

    # Assert
    assert task.id == "task-1"
    assert task.thinking[0]["content"] == "Inspect first, then implement."


def test_pairs_parallel_tool_results_by_id_when_results_are_reordered() -> None:
    # Arrange
    records = [
        {"type": "user", "uuid": "user-1", "message": {"role": "user", "content": "Inspect"}},
        {
            "type": "assistant",
            "uuid": "assistant-1",
            "message": {
                "role": "assistant",
                "content": [
                    {"type": "tool_use", "id": "tool-1", "name": "Read", "input": {"file_path": "a"}},
                    {"type": "tool_use", "id": "tool-2", "name": "Read", "input": {"file_path": "b"}},
                ],
            },
        },
        {
            "type": "user",
            "uuid": "user-2",
            "message": {
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": "tool-2", "content": "B"},
                    {"type": "tool_result", "tool_use_id": "tool-1", "content": "A"},
                ],
            },
        },
    ]

    # Act
    loop = ExecutionTraceProjector().project(records).tasks[0].loops[0]

    # Assert
    results = [event for event in loop.events if event.type == ExecutionEventType.TOOL_RESULT]
    assert [(event.tool_use_id, event.content) for event in results] == [("tool-2", "B"), ("tool-1", "A")]


def test_projects_explicit_tasks_and_dependencies_when_task_tools_are_present() -> None:
    # Arrange
    records = [
        {
            "type": "assistant",
            "uuid": "assistant-1",
            "message": {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "task-create",
                        "name": "TaskCreate",
                        "input": {
                            "taskId": "task-2",
                            "subject": "Implement projector",
                            "description": "Build domain projection",
                            "status": "in_progress",
                            "blockedBy": ["task-1"],
                        },
                    }
                ],
            },
        },
        {
            "type": "assistant",
            "uuid": "assistant-2",
            "message": {"role": "assistant", "content": "Working on the explicit task"},
        },
        {
            "type": "assistant",
            "uuid": "assistant-3",
            "message": {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "task-update",
                        "name": "TaskUpdate",
                        "input": {"taskId": "task-2", "status": "completed", "addBlockedBy": ["task-0"]},
                    }
                ],
            },
        },
    ]

    # Act
    projection = ExecutionTraceProjector().project(records)

    # Assert
    explicit = next(task for task in projection.tasks if task.id == "task-2")
    assert explicit.subject == "Implement projector"
    assert explicit.status == "completed"
    assert explicit.loops[0].id == "loop-assistant-2"
    assert {(edge.task_id, edge.depends_on_task_id) for edge in projection.dependencies} == {
        ("task-2", "task-1"),
        ("task-2", "task-0"),
    }


def test_merges_task_status_when_create_result_assigns_task_id() -> None:
    # Arrange
    records = [
        {
            "type": "assistant",
            "uuid": "assistant-plan",
            "message": {
                "role": "assistant",
                "content": [{
                    "type": "tool_use",
                    "id": "create-1",
                    "name": "TaskCreate",
                    "input": {"subject": "Implement projector", "description": "Build it"},
                }],
            },
        },
        {
            "type": "user",
            "uuid": "user-create-result",
            "message": {
                "role": "user",
                "content": [{
                    "type": "tool_result",
                    "tool_use_id": "create-1",
                    "content": "Task #1 created successfully: Implement projector",
                }],
            },
        },
        {
            "type": "assistant",
            "uuid": "assistant-start",
            "message": {
                "role": "assistant",
                "content": [{
                    "type": "tool_use",
                    "id": "update-start",
                    "name": "TaskUpdate",
                    "input": {"taskId": "1", "status": "in_progress"},
                }],
            },
        },
        {
            "type": "assistant",
            "uuid": "assistant-work",
            "message": {
                "role": "assistant",
                "content": [{
                    "type": "tool_use",
                    "id": "read-1",
                    "name": "Read",
                    "input": {"file_path": "projector.py"},
                }],
            },
        },
        {
            "type": "assistant",
            "uuid": "assistant-complete",
            "message": {
                "role": "assistant",
                "content": [{
                    "type": "tool_use",
                    "id": "update-complete",
                    "name": "TaskUpdate",
                    "input": {"taskId": "1", "status": "completed"},
                }],
            },
        },
    ]

    # Act
    projection = ExecutionTraceProjector().project(records)

    # Assert
    assert [(task.id, task.subject, task.status) for task in projection.tasks] == [
        ("1", "Implement projector", "completed"),
    ]
    assert projection.tasks[0].loops
    assert all(loop.task_id == "1" for loop in projection.tasks[0].loops)
    assert any(
        event.tool_name == "Read"
        for loop in projection.tasks[0].loops
        for event in loop.events
    )


def test_ignores_status_update_when_task_was_not_planned() -> None:
    # Arrange
    records = [{
        "type": "assistant",
        "uuid": "assistant-1",
        "message": {
            "role": "assistant",
            "content": [{
                "type": "tool_use",
                "id": "update-unknown",
                "name": "TaskUpdate",
                "input": {"taskId": "99", "status": "completed"},
            }],
        },
    }]

    # Act
    projection = ExecutionTraceProjector().project(records)

    # Assert
    assert all(task.id != "99" for task in projection.tasks)
    assert "unknown_task_update:99" in projection.provenance.warnings


def test_calculates_step_duration_when_tool_result_has_timestamp() -> None:
    # Arrange
    records = [
        {
            "type": "user",
            "uuid": "user-1",
            "timestamp": "2026-07-19T10:00:00.000Z",
            "message": {"role": "user", "content": "Inspect"},
        },
        {
            "type": "assistant",
            "uuid": "assistant-1",
            "timestamp": "2026-07-19T10:00:01.250Z",
            "message": {
                "role": "assistant",
                "content": [{
                    "type": "tool_use",
                    "id": "read-1",
                    "name": "Read",
                    "input": {"file_path": "app.py"},
                }],
            },
        },
        {
            "type": "user",
            "uuid": "user-2",
            "timestamp": "2026-07-19T10:00:03.500Z",
            "message": {
                "role": "user",
                "content": [{
                    "type": "tool_result",
                    "tool_use_id": "read-1",
                    "content": {"lines": 12},
                }],
            },
        },
    ]

    # Act
    loop = ExecutionTraceProjector().project(records).tasks[0].loops[0]

    # Assert
    assert loop.duration_ms == 3500


def test_returns_lazy_subagent_placeholder_when_agent_tool_has_trace_metadata() -> None:
    # Arrange
    span = TraceSpan.create(
        session_id="session-1",
        run_id="run-1",
        span_type=TraceSpan.SPAN_TYPE_SUBAGENT,
        name="researcher",
        agent_id="agent-1",
        tool_use_id="agent-tool",
        metadata={"subagent": "researcher", "transcript_path": "/tmp/agent.jsonl"},
    )
    records = [
        {
            "type": "assistant",
            "uuid": "assistant-1",
            "message": {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "agent-tool",
                        "name": "Agent",
                        "input": {"subagent_type": "fallback"},
                    }
                ],
            },
        }
    ]

    # Act
    placeholder = ExecutionTraceProjector().project(records, spans=[span]).subagents[0]

    # Assert
    assert placeholder.tool_use_id == "agent-tool"
    assert placeholder.subagent == "researcher"
    assert placeholder.agent_id == "agent-1"
    assert placeholder.transcript_path == "/tmp/agent.jsonl"
    assert placeholder.span_id == span.id
    assert placeholder.is_expandable is True


def test_reports_next_cursor_when_loop_detail_exceeds_limit() -> None:
    # Arrange
    records = [
        {
            "type": "assistant",
            "uuid": "assistant-1",
            "message": {
                "role": "assistant",
                "content": [
                    {"type": "tool_use", "id": "tool-1", "name": "Read", "input": {}},
                    {"type": "tool_use", "id": "tool-2", "name": "Read", "input": {}},
                ],
            },
        }
    ]
    loop = ExecutionTraceProjector().project(records).tasks[0].loops[0]

    # Act
    first_page = loop.detail_page(cursor=0, limit=2)
    second_page = loop.detail_page(cursor=first_page.next_cursor or 0, limit=2)

    # Assert
    assert first_page.total == 4
    assert first_page.next_cursor == 2
    assert len(first_page.items) == 2
    assert second_page.next_cursor is None
    assert len(second_page.items) == 2


def test_marks_projection_partial_when_tool_result_is_missing() -> None:
    # Arrange
    records = [
        {
            "type": "assistant",
            "uuid": "assistant-1",
            "message": {
                "role": "assistant",
                "content": [{"type": "tool_use", "id": "tool-1", "name": "Read", "input": {}}],
            },
        }
    ]

    # Act
    projection = ExecutionTraceProjector().project(records)

    # Assert
    assert projection.provenance.completeness == ProjectionCompleteness.PARTIAL
    assert projection.provenance.warnings == ("missing_tool_result:tool-1",)
