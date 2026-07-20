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


def test_uses_direct_parent_message_as_input_for_each_agent_loop() -> None:
    # Arrange
    records = [
        {"type": "user", "uuid": "user-request", "message": {"role": "user", "content": "Inspect"}},
        {"type": "assistant", "uuid": "assistant-read", "parentUuid": "user-request", "message": {"role": "assistant", "content": [
            {"type": "tool_use", "id": "read-1", "name": "Read", "input": {"file_path": "app.py"}},
        ]}},
        {"type": "user", "uuid": "user-result", "parentUuid": "assistant-read", "message": {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "read-1", "content": "file contents"},
        ]}},
        {"type": "assistant", "uuid": "assistant-final", "parentUuid": "user-result", "message": {"role": "assistant", "content": "Done"}},
    ]

    # Act
    loops = ExecutionTraceProjector().project(records).tasks[0].loops

    # Assert
    assert loops[0].model_input[0]["uuid"] == "user-request"
    assert loops[1].model_input[0]["uuid"] == "user-result"
    assert len(loops[1].model_input) == 1


def test_coalesces_parent_linked_assistant_fragments_into_complete_turn() -> None:
    # Arrange
    records = [
        {"type": "user", "uuid": "user-1", "message": {"role": "user", "content": "Inspect"}},
        {"type": "assistant", "uuid": "thinking-1", "parentUuid": "user-1", "message": {"role": "assistant", "content": [
            {"type": "thinking", "thinking": "I should read the file."},
        ]}},
        {"type": "assistant", "uuid": "text-1", "parentUuid": "thinking-1", "message": {"role": "assistant", "content": [
            {"type": "text", "text": "I will inspect it."},
        ]}},
        {"type": "assistant", "uuid": "tool-1-record", "parentUuid": "text-1", "message": {"role": "assistant", "content": [
            {"type": "tool_use", "id": "read-1", "name": "Read", "input": {"file_path": "app.py"}},
        ]}},
        {"type": "user", "uuid": "result-1", "parentUuid": "tool-1-record", "message": {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "read-1", "content": "file contents"},
        ]}},
    ]

    # Act
    task = ExecutionTraceProjector().project(records).tasks[0]

    # Assert
    assert len(task.loops) == 1
    assert [block["type"] for block in task.loops[0].assistant_content] == ["thinking", "text", "tool_use"]
    assert [event.type for event in task.loops[0].events] == [
        ExecutionEventType.MODEL_INPUT,
        ExecutionEventType.THINKING,
        ExecutionEventType.MODEL_OUTPUT,
        ExecutionEventType.TOOL_USE,
        ExecutionEventType.TOOL_RESULT,
    ]


def test_keeps_planning_and_final_response_loops_when_explicit_tasks_exist() -> None:
    # Arrange
    records = [
        {"type": "assistant", "uuid": "plan", "message": {"role": "assistant", "content": [
            {"type": "tool_use", "id": "create-1", "name": "TaskCreate", "input": {"taskId": "1", "subject": "Inspect"}},
        ]}},
        {"type": "assistant", "uuid": "start", "message": {"role": "assistant", "content": [
            {"type": "tool_use", "id": "start-1", "name": "TaskUpdate", "input": {"taskId": "1", "status": "in_progress"}},
        ]}},
        {"type": "assistant", "uuid": "work", "message": {"role": "assistant", "content": [
            {"type": "tool_use", "id": "read-1", "name": "Read", "input": {"file_path": "app.py"}},
        ]}},
        {"type": "assistant", "uuid": "complete", "message": {"role": "assistant", "content": [
            {"type": "tool_use", "id": "complete-1", "name": "TaskUpdate", "input": {"taskId": "1", "status": "completed"}},
        ]}},
        {"type": "assistant", "uuid": "final", "message": {"role": "assistant", "content": "Implemented and verified."}},
    ]

    # Act
    loops = ExecutionTraceProjector().project(records).tasks[0].loops

    # Assert
    assert [loop.id for loop in loops] == ["loop-plan", "loop-start", "loop-work", "loop-complete", "loop-final"]
    assert [loop.sequence for loop in loops] == [1, 2, 3, 4, 5]


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


def test_attaches_planning_event_to_first_step_when_explicit_task_exists() -> None:
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
    planning_events = [
        event
        for event in task.loops[0].events
        if event.type == ExecutionEventType.THINKING
    ]
    assert planning_events[0].content == "Inspect first, then implement."


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
    assert [loop.id for loop in explicit.loops] == [
        "loop-assistant-1",
        "loop-assistant-2",
        "loop-assistant-3",
    ]
    assert {(edge.task_id, edge.depends_on_task_id) for edge in projection.dependencies} == {
        ("task-2", "task-1"),
        ("task-2", "task-0"),
    }


def test_projects_all_tasks_created_for_one_user_message() -> None:
    # Arrange
    records = [
        {"type": "user", "uuid": "user-current", "message": {"role": "user", "content": "Implement and verify"}},
        {
            "type": "assistant",
            "uuid": "assistant-plan",
            "message": {"role": "assistant", "content": [
                {"type": "tool_use", "id": "create-1", "name": "TaskCreate", "input": {"taskId": "1", "subject": "Implement"}},
                {"type": "tool_use", "id": "create-2", "name": "TaskCreate", "input": {"taskId": "2", "subject": "Verify"}},
            ]},
        },
    ]

    # Act
    projection = ExecutionTraceProjector().project(records)

    # Assert
    assert [task.subject for task in projection.tasks] == ["Implement", "Verify"]
    assert projection.request == "Implement and verify"


def test_preserves_multi_task_plan_with_descriptions_and_owned_steps() -> None:
    # Arrange
    records = [
        {"type": "user", "uuid": "user-plan", "message": {"role": "user", "content": "Implement, test, and document the feature"}},
        {
            "type": "assistant",
            "uuid": "assistant-plan",
            "message": {"role": "assistant", "content": [
                {"type": "thinking", "thinking": "Split implementation, verification, and documentation."},
                {"type": "tool_use", "id": "create-1", "name": "TaskCreate", "input": {"taskId": "1", "subject": "Implement feature", "description": "Change the production code"}},
                {"type": "tool_use", "id": "create-2", "name": "TaskCreate", "input": {"taskId": "2", "subject": "Verify feature", "description": "Run focused and regression tests"}},
                {"type": "tool_use", "id": "create-3", "name": "TaskCreate", "input": {"taskId": "3", "subject": "Document feature", "description": "Explain behavior and handoff"}},
            ]},
        },
        {"type": "assistant", "uuid": "start-1", "message": {"role": "assistant", "content": [{"type": "tool_use", "id": "start-tool-1", "name": "TaskUpdate", "input": {"taskId": "1", "status": "in_progress"}}]}},
        {"type": "assistant", "uuid": "work-1", "message": {"role": "assistant", "content": [{"type": "tool_use", "id": "edit-1", "name": "Edit", "input": {"file_path": "feature.py"}}]}},
        {"type": "assistant", "uuid": "done-1", "message": {"role": "assistant", "content": [{"type": "tool_use", "id": "done-tool-1", "name": "TaskUpdate", "input": {"taskId": "1", "status": "completed"}}]}},
        {"type": "assistant", "uuid": "start-2", "message": {"role": "assistant", "content": [{"type": "tool_use", "id": "start-tool-2", "name": "TaskUpdate", "input": {"taskId": "2", "status": "in_progress"}}]}},
        {"type": "assistant", "uuid": "work-2", "message": {"role": "assistant", "content": [{"type": "tool_use", "id": "test-1", "name": "Bash", "input": {"command": "pytest"}}]}},
        {"type": "assistant", "uuid": "done-2", "message": {"role": "assistant", "content": [{"type": "tool_use", "id": "done-tool-2", "name": "TaskUpdate", "input": {"taskId": "2", "status": "completed"}}]}},
        {"type": "assistant", "uuid": "start-3", "message": {"role": "assistant", "content": [{"type": "tool_use", "id": "start-tool-3", "name": "TaskUpdate", "input": {"taskId": "3", "status": "in_progress"}}]}},
        {"type": "assistant", "uuid": "work-3", "message": {"role": "assistant", "content": [{"type": "tool_use", "id": "write-1", "name": "Write", "input": {"file_path": "README.md"}}]}},
        {"type": "assistant", "uuid": "done-3", "message": {"role": "assistant", "content": [{"type": "tool_use", "id": "done-tool-3", "name": "TaskUpdate", "input": {"taskId": "3", "status": "completed"}}]}},
    ]

    # Act
    projection = ExecutionTraceProjector().project(records)

    # Assert
    assert [(task.id, task.subject, task.description, task.status) for task in projection.tasks] == [
        ("1", "Implement feature", "Change the production code", "completed"),
        ("2", "Verify feature", "Run focused and regression tests", "completed"),
        ("3", "Document feature", "Explain behavior and handoff", "completed"),
    ]
    assert [task.loops[-2].tool_names for task in projection.tasks] == [("Edit",), ("Bash",), ("Write",)]


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


def test_resolves_subagent_span_from_parent_tool_when_subagent_has_no_tool_use_id() -> None:
    # Arrange
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
    )
    records = [{
        "type": "assistant",
        "uuid": "assistant-1",
        "message": {"role": "assistant", "content": [{
            "type": "tool_use",
            "id": "agent-tool",
            "name": "Agent",
            "input": {"subagent_type": "researcher", "prompt": "Inspect"},
        }]},
    }]

    # Act
    placeholder = ExecutionTraceProjector().project(records, spans=[tool, subagent]).subagents[0]

    # Assert
    assert placeholder.span_id == subagent.id
    assert placeholder.is_expandable is True


def test_projects_task_tool_as_subagent_when_it_has_agent_input() -> None:
    records = [{
        "type": "assistant",
        "uuid": "assistant-task-agent",
        "message": {
            "role": "assistant",
            "content": [{
                "type": "tool_use",
                "id": "subagent-tool",
                "name": "Task",
                "input": {"subagent_type": "researcher", "prompt": "Inspect the code"},
            }],
        },
    }]

    loop = ExecutionTraceProjector().project(records).tasks[0].loops[0]

    assert any(event.type == ExecutionEventType.SUBAGENT for event in loop.events)


def test_projects_overloaded_task_tool_as_multiple_managed_tasks() -> None:
    # Arrange
    records = [{
        "type": "assistant",
        "uuid": "assistant-task-plan",
        "message": {
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "id": "task-create-1",
                    "name": "Task",
                    "input": {"subject": "Inspect backend", "description": "Find the projection bug", "activeForm": "Inspecting backend"},
                },
                {
                    "type": "tool_use",
                    "id": "task-create-2",
                    "name": "Task",
                    "input": {"subject": "Verify frontend", "description": "Check the rendered tree", "activeForm": "Verifying frontend"},
                },
            ],
        },
    }]

    # Act
    projection = ExecutionTraceProjector().project(records)

    # Assert
    assert [task.subject for task in projection.tasks] == ["Inspect backend", "Verify frontend"]
    assert projection.subagents == ()


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


def test_projects_first_error_message_to_loop_when_tool_result_fails() -> None:
    # Arrange
    records = [
        {"type": "assistant", "uuid": "assistant-1", "message": {"role": "assistant", "content": [
            {"type": "tool_use", "id": "tool-1", "name": "Read", "input": {"file_path": "missing"}},
        ]}},
        {"type": "user", "uuid": "user-1", "message": {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "tool-1", "is_error": True, "content": {"error": {"message": "File not found"}}},
        ]}},
    ]

    # Act
    loop = ExecutionTraceProjector().project(records).tasks[0].loops[0]

    # Assert
    assert loop.error_message == "File not found"
    assert loop.events[-1].error_message == "File not found"


def test_truncates_error_message_when_tool_result_error_is_too_long() -> None:
    # Arrange
    message = "x" * 2_100
    records = [
        {"type": "assistant", "uuid": "assistant-1", "message": {"role": "assistant", "content": [
            {"type": "tool_use", "id": "tool-1", "name": "Read", "input": {}},
        ]}},
        {"type": "user", "uuid": "user-1", "message": {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "tool-1", "is_error": True, "content": {"detail": message}},
        ]}},
    ]

    # Act
    error_message = ExecutionTraceProjector().project(records).tasks[0].loops[0].error_message

    # Assert
    assert error_message == f"{'x' * 1_997}..."
