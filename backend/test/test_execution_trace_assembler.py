from domain.session.model.execution_trace import (
    AgentLoop,
    ExecutionAgent,
    ExecutionTask,
    ProjectionProvenance,
)
from ohs.http.assembler.execution_trace_assembler import ExecutionTraceAssembler


def test_numbers_steps_in_task_order_when_assembling_tree() -> None:
    # Arrange
    loops = tuple(
        AgentLoop(
            id=f"loop-{index}",
            task_id="task-1",
            model_input=(),
            assistant_content=(),
            events=(),
            model=None,
            stop_reason=None,
            usage={},
            provenance=ProjectionProvenance(),
        )
        for index in range(3)
    )
    task = ExecutionTask("task-1", "Implement", None, "completed", True, loops)
    agent = ExecutionAgent("main", (task,), (), (), ProjectionProvenance())

    # Act
    response = ExecutionTraceAssembler.to_tree_response(agent)

    # Assert
    assert [loop.sequence for loop in response.tasks[0].loops] == [1, 2, 3]


def test_maps_loop_error_message_when_assembling_tree() -> None:
    # Arrange
    loop = AgentLoop(
        id="loop-1", task_id="task-1", model_input=(), assistant_content=(), events=(),
        model=None, stop_reason=None, usage={}, provenance=ProjectionProvenance(),
        error_message="Permission denied",
    )
    task = ExecutionTask("task-1", "Implement", None, "failed", True, (loop,))
    agent = ExecutionAgent("main", (task,), (), (), ProjectionProvenance())

    # Act
    response = ExecutionTraceAssembler.to_tree_response(agent)

    # Assert
    assert response.tasks[0].loops[0].error_message == "Permission denied"
