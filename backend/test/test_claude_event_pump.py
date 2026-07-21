from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest
from claude_agent_sdk.types import (
    ResultMessage,
    TaskNotificationMessage,
    TaskProgressMessage,
    TaskStartedMessage,
    TaskUsage,
)

from infr.client.claude_event_pump import ClaudeConnectionEventPump, TurnPhase


_STREAM_END = object()


class _QueueClient:
    def __init__(self) -> None:
        self._queue: asyncio.Queue[object] = asyncio.Queue()

    async def receive_messages(self) -> AsyncIterator[object]:
        while True:
            message = await self._queue.get()
            if message is _STREAM_END:
                return
            if isinstance(message, BaseException):
                raise message
            yield message

    async def emit(self, message: object) -> None:
        await self._queue.put(message)

    async def end(self) -> None:
        await self._queue.put(_STREAM_END)


def _result(text: str, *, is_error: bool = False) -> ResultMessage:
    return ResultMessage(
        subtype="error" if is_error else "success",
        duration_ms=1,
        duration_api_ms=1,
        is_error=is_error,
        num_turns=1,
        session_id="sdk-session",
        result=text,
        usage={"input_tokens": 1, "output_tokens": 1},
    )


def _task_started(task_id: str) -> TaskStartedMessage:
    return TaskStartedMessage(
        subtype="task_started",
        data={},
        task_id=task_id,
        description=f"Run {task_id}",
        uuid=f"started-{task_id}",
        session_id="sdk-session",
    )


def _task_progress(task_id: str) -> TaskProgressMessage:
    return TaskProgressMessage(
        subtype="task_progress",
        data={},
        task_id=task_id,
        description=f"Run {task_id}",
        usage=TaskUsage(total_tokens=10, tool_uses=1, duration_ms=50),
        uuid=f"progress-{task_id}",
        session_id="sdk-session",
    )


def _task_finished(task_id: str, status: str = "completed") -> TaskNotificationMessage:
    return TaskNotificationMessage(
        subtype="task_notification",
        data={},
        task_id=task_id,
        status=status,
        output_file=f"/tmp/{task_id}.output",
        summary=f"{task_id} {status}",
        uuid=f"notification-{task_id}",
        session_id="sdk-session",
    )


async def _collect(turn) -> list[object]:
    return [message async for message in turn.messages()]


@pytest.mark.asyncio
async def test_returns_result_when_turn_has_no_background_tasks() -> None:
    # Arrange
    client = _QueueClient()
    pump = ClaudeConnectionEventPump("session-1", client, result_settle_seconds=0)
    pump.start()
    turn = await pump.begin_turn()

    # Act
    await client.emit(_result("done"))
    messages = await asyncio.wait_for(_collect(turn), timeout=1)
    await pump.close()

    # Assert
    assert [message.result for message in messages] == ["done"]


@pytest.mark.asyncio
async def test_waits_for_final_result_when_background_task_is_running() -> None:
    # Arrange
    client = _QueueClient()
    pump = ClaudeConnectionEventPump("session-1", client, result_settle_seconds=0.05)
    pump.start()
    turn = await pump.begin_turn()

    # Act
    for message in (
        _task_started("task-1"),
        _result("intermediate"),
        _task_progress("task-1"),
        _task_finished("task-1"),
        _result("final"),
    ):
        await client.emit(message)
    messages = await asyncio.wait_for(_collect(turn), timeout=1)
    await pump.close()

    # Assert
    results = [message for message in messages if isinstance(message, ResultMessage)]
    assert [message.result for message in results] == ["final"]


@pytest.mark.asyncio
async def test_waits_until_every_background_task_is_terminal() -> None:
    # Arrange
    client = _QueueClient()
    pump = ClaudeConnectionEventPump("session-1", client, result_settle_seconds=0.05)
    pump.start()
    turn = await pump.begin_turn()
    collector = asyncio.create_task(_collect(turn))

    # Act
    for message in (
        _task_started("task-1"),
        _task_started("task-2"),
        _result("intermediate"),
        _task_finished("task-1"),
    ):
        await client.emit(message)
    await asyncio.sleep(0.01)
    still_waiting = not collector.done()
    await client.emit(_task_finished("task-2", status="failed"))
    await client.emit(_result("final"))
    await asyncio.wait_for(collector, timeout=1)
    await pump.close()

    # Assert
    assert still_waiting is True


@pytest.mark.asyncio
async def test_uses_deferred_result_when_sdk_omits_second_result() -> None:
    # Arrange
    client = _QueueClient()
    pump = ClaudeConnectionEventPump(
        "session-1",
        client,
        result_settle_seconds=0.05,
        final_result_timeout_seconds=0.01,
    )
    pump.start()
    turn = await pump.begin_turn()

    # Act
    await client.emit(_task_started("task-1"))
    await client.emit(_result("deferred"))
    await client.emit(_task_finished("task-1"))
    messages = await asyncio.wait_for(_collect(turn), timeout=1)
    await pump.close()

    # Assert
    results = [message for message in messages if isinstance(message, ResultMessage)]
    assert [message.result for message in results] == ["deferred"]


@pytest.mark.asyncio
async def test_fails_turn_when_background_task_exceeds_deadline() -> None:
    # Arrange
    client = _QueueClient()
    pump = ClaudeConnectionEventPump(
        "session-1",
        client,
        background_task_timeout_seconds=0.01,
    )
    pump.start()
    turn = await pump.begin_turn()

    # Act
    await client.emit(_task_started("task-1"))
    messages = await asyncio.wait_for(_collect(turn), timeout=1)
    await pump.close()

    # Assert
    result = next(message for message in messages if isinstance(message, dict) and message.get("type") == "result")
    assert result["stop_reason"] == "background_task_timeout"


@pytest.mark.asyncio
async def test_drops_late_notification_instead_of_routing_it_to_next_turn() -> None:
    # Arrange
    client = _QueueClient()
    pump = ClaudeConnectionEventPump("session-1", client, result_settle_seconds=0)
    pump.start()
    first_turn = await pump.begin_turn()
    await client.emit(_result("first"))
    await asyncio.wait_for(_collect(first_turn), timeout=1)

    # Act
    await client.emit(_task_finished("late-task"))
    second_turn = await pump.begin_turn()
    await client.emit(_result("second"))
    messages = await asyncio.wait_for(_collect(second_turn), timeout=1)
    await pump.close()

    # Assert
    assert [message.result for message in messages] == ["second"]


@pytest.mark.asyncio
async def test_rejects_second_turn_while_first_turn_is_active() -> None:
    # Arrange
    client = _QueueClient()
    pump = ClaudeConnectionEventPump("session-1", client)
    pump.start()
    await pump.begin_turn()

    # Act / Assert
    with pytest.raises(RuntimeError, match="already active"):
        await pump.begin_turn()
    await pump.close()


@pytest.mark.asyncio
async def test_propagates_reader_failure_to_active_turn() -> None:
    # Arrange
    client = _QueueClient()
    pump = ClaudeConnectionEventPump("session-1", client)
    pump.start()
    turn = await pump.begin_turn()

    # Act
    await client.emit(RuntimeError("reader failed"))

    # Assert
    with pytest.raises(RuntimeError, match="reader failed"):
        await asyncio.wait_for(_collect(turn), timeout=1)
    await pump.close()


@pytest.mark.asyncio
async def test_interrupt_allows_result_to_terminate_with_running_tasks() -> None:
    # Arrange
    phases: list[TurnPhase] = []
    client = _QueueClient()
    pump = ClaudeConnectionEventPump("session-1", client, phase_changed=phases.append)
    pump.start()
    turn = await pump.begin_turn()
    await client.emit(_task_started("task-1"))

    # Act
    await pump.interrupt_turn()
    await client.emit(_result("interrupted"))
    messages = await asyncio.wait_for(_collect(turn), timeout=1)
    await pump.close()

    # Assert
    assert isinstance(messages[-1], ResultMessage)
    assert TurnPhase.INTERRUPTED in phases


@pytest.mark.asyncio
async def test_transitions_through_background_task_phases() -> None:
    # Arrange
    phases: list[TurnPhase] = []
    client = _QueueClient()
    pump = ClaudeConnectionEventPump(
        "session-1",
        client,
        phase_changed=phases.append,
        result_settle_seconds=0.05,
    )
    pump.start()
    turn = await pump.begin_turn()

    # Act
    await client.emit(_task_started("task-1"))
    await client.emit(_result("intermediate"))
    await client.emit(_task_finished("task-1"))
    await client.emit(_result("final"))
    await asyncio.wait_for(_collect(turn), timeout=1)
    await pump.close()

    # Assert
    assert phases == [
        TurnPhase.STREAMING,
        TurnPhase.WAITING_BACKGROUND,
        TurnPhase.AWAITING_FINAL_RESULT,
        TurnPhase.TERMINAL,
    ]


@pytest.mark.asyncio
async def test_unblocks_active_turn_when_connection_pump_closes() -> None:
    # Arrange
    client = _QueueClient()
    pump = ClaudeConnectionEventPump("session-1", client)
    pump.start()
    turn = await pump.begin_turn()

    # Act
    await pump.close()

    # Assert
    with pytest.raises(ConnectionError, match="connection closed"):
        await asyncio.wait_for(_collect(turn), timeout=1)
