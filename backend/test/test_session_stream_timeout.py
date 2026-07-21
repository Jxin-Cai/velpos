from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from application.session.session_stream_consumer import SessionStreamConsumer


@pytest.mark.asyncio
async def test_releases_stalled_stream_when_silence_limit_is_reached(monkeypatch):
    # Arrange
    monkeypatch.setenv("CLAUDE_STREAM_MESSAGE_TIMEOUT_SECONDS", "0.01")
    monkeypatch.setenv("CLAUDE_STREAM_MAX_SILENT_TIMEOUTS", "2")
    recorder = SimpleNamespace(
        start_run_step=AsyncMock(return_value=SimpleNamespace()),
        record_audit_event=AsyncMock(),
        record_timeline_event=AsyncMock(),
        fail_run_step=AsyncMock(),
    )
    gateway = SimpleNamespace(
        update_trace_run_id=Mock(),
        is_process_alive=Mock(return_value=True),
        is_waiting_for_user_input=Mock(return_value=False),
        is_waiting_for_background_tasks=Mock(return_value=False),
        disconnect=AsyncMock(),
    )
    consumer = SessionStreamConsumer(
        recorder=recorder,
        claude_agent_gateway=gateway,
        connection_manager=SimpleNamespace(broadcast=AsyncMock()),
        save_session_fn=AsyncMock(),
        accept_sdk_session_id_fn=AsyncMock(),
        cancelled_sessions=set(),
    )
    session = SimpleNamespace(session_id="session-1")

    async def silent_stream():
        await asyncio.Event().wait()
        yield {}

    # Act / Assert
    with pytest.raises(TimeoutError, match="produced no output"):
        await consumer.consume(session, silent_stream(), "run-1")

    gateway.disconnect.assert_awaited_once_with("session-1")


def test_disables_silence_limit_when_not_configured(monkeypatch):
    # Arrange
    monkeypatch.delenv("CLAUDE_STREAM_MAX_SILENT_TIMEOUTS", raising=False)

    # Act
    consumer = SessionStreamConsumer(
        recorder=Mock(),
        claude_agent_gateway=Mock(),
        connection_manager=Mock(),
        save_session_fn=AsyncMock(),
        accept_sdk_session_id_fn=AsyncMock(),
        cancelled_sessions=set(),
    )

    # Assert
    assert consumer._max_silent_timeouts == 0


@pytest.mark.asyncio
async def test_keeps_stream_open_when_waiting_for_background_tasks(monkeypatch):
    # Arrange
    monkeypatch.setenv("CLAUDE_STREAM_MAX_SILENT_TIMEOUTS", "1")
    recorder = SimpleNamespace(
        start_run_step=AsyncMock(return_value=SimpleNamespace()),
        record_audit_event=AsyncMock(),
        record_timeline_event=AsyncMock(),
        fail_run_step=AsyncMock(),
    )
    gateway = SimpleNamespace(
        update_trace_run_id=Mock(),
        is_process_alive=Mock(return_value=True),
        is_waiting_for_user_input=Mock(return_value=False),
        is_waiting_for_background_tasks=Mock(return_value=True),
        disconnect=AsyncMock(),
    )
    consumer = SessionStreamConsumer(
        recorder=recorder,
        claude_agent_gateway=gateway,
        connection_manager=SimpleNamespace(broadcast=AsyncMock()),
        save_session_fn=AsyncMock(),
        accept_sdk_session_id_fn=AsyncMock(),
        cancelled_sessions=set(),
    )
    consumer._stream_msg_timeout = 0.01
    session = SimpleNamespace(session_id="session-1")

    async def silent_stream():
        await asyncio.Event().wait()
        yield {}

    # Act
    consume_task = asyncio.create_task(consumer.consume(session, silent_stream(), "run-1"))
    await asyncio.sleep(0.04)
    still_waiting = not consume_task.done()
    consume_task.cancel()
    await asyncio.gather(consume_task, return_exceptions=True)

    # Assert
    assert still_waiting is True
    gateway.disconnect.assert_not_awaited()
