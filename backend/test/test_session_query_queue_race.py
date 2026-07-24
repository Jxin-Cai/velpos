from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from application.session.command.run_query_command import RunQueryCommand
from application.session.session_query_engine import QueueMessageOutcome, SessionQueryEngine


def _engine() -> SessionQueryEngine:
    return SessionQueryEngine(
        session_repository=Mock(),
        claude_agent_gateway=Mock(),
        connection_manager=Mock(),
        recorder=Mock(),
        stream_consumer=Mock(),
        save_session_fn=AsyncMock(),
        reconnect_db_session_fn=AsyncMock(),
        accept_or_reject_sdk_session_id_fn=AsyncMock(),
        resolve_resume_sdk_session_id_fn=AsyncMock(),
        refresh_context_usage_fn=AsyncMock(),
    )


@pytest.mark.asyncio
async def test_runs_message_immediately_when_active_context_has_finished() -> None:
    # Arrange
    session_id = "finished-session"
    command = RunQueryCommand(
        session_id=session_id,
        prompt="next request",
        client_message_id="message-next",
    )
    engine = _engine()
    async with SessionQueryEngine._queue_guard:
        SessionQueryEngine._active_contexts.pop(session_id, None)
        SessionQueryEngine._queued_messages.pop(session_id, None)

    # Act
    outcome = await engine.queue_message(session_id, command)

    # Assert
    assert outcome is QueueMessageOutcome.RUN_IMMEDIATELY


@pytest.mark.asyncio
async def test_queues_message_when_active_context_still_exists() -> None:
    # Arrange
    session_id = "active-session"
    command = RunQueryCommand(
        session_id=session_id,
        prompt="follow up",
        client_message_id="message-follow-up",
    )
    engine = _engine()
    engine._set_queued_command = AsyncMock()
    engine._recorder = SimpleNamespace(record_audit_event=AsyncMock())
    active_context = object()
    async with SessionQueryEngine._queue_guard:
        SessionQueryEngine._active_contexts[session_id] = active_context
        SessionQueryEngine._queued_messages.pop(session_id, None)

    try:
        # Act
        outcome = await engine.queue_message(session_id, command)

        # Assert
        assert outcome is QueueMessageOutcome.QUEUED
    finally:
        async with SessionQueryEngine._queue_guard:
            SessionQueryEngine._active_contexts.pop(session_id, None)
            SessionQueryEngine._queued_messages.pop(session_id, None)
