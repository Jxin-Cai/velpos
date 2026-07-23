from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from application.session.command.run_query_command import RunQueryCommand
from application.session.session_query_engine import SessionQueryEngine
from domain.session.model.message import Message
from domain.session.model.message_type import MessageType
from domain.session.model.session import Session
from domain.shared.business_exception import BusinessException


def _engine(session: Session) -> SessionQueryEngine:
    return SessionQueryEngine(
        session_repository=SimpleNamespace(find_by_id=AsyncMock(return_value=session)),
        claude_agent_gateway=Mock(),
        connection_manager=SimpleNamespace(broadcast=AsyncMock()),
        recorder=Mock(),
        stream_consumer=Mock(),
        save_session_fn=AsyncMock(),
        reconnect_db_session_fn=AsyncMock(),
        accept_or_reject_sdk_session_id_fn=AsyncMock(),
        resolve_resume_sdk_session_id_fn=AsyncMock(),
        refresh_context_usage_fn=AsyncMock(),
    )


def _completed_session() -> Session:
    session = Session.create()
    session.add_message(
        Message.create(
            MessageType.USER,
            {
                "message_id": "message-1",
                "raw_prompt": "hello",
                "text": "hello",
                "attachments": [],
            },
        )
    )
    session.add_message(
        Message.create(
            MessageType.RESULT,
            {"is_error": False, "text": "done"},
        )
    )
    return session


@pytest.mark.asyncio
async def test_acknowledges_completed_query_when_client_message_id_is_retried():
    # Arrange
    engine = _engine(_completed_session())
    command = RunQueryCommand(
        session_id="session1",
        prompt="hello",
        client_message_id="message-1",
    )

    # Act
    completed = await engine._acknowledge_terminal_duplicate(command)

    # Assert
    assert completed is True
    event = engine._connection_manager.broadcast.await_args.args[1]
    assert event["completed"] is True


@pytest.mark.asyncio
async def test_rejects_client_message_id_when_prompt_content_changes():
    # Arrange
    engine = _engine(_completed_session())
    command = RunQueryCommand(
        session_id="session1",
        prompt="different",
        client_message_id="message-1",
    )

    # Act / Assert
    with pytest.raises(BusinessException) as error:
        await engine._acknowledge_terminal_duplicate(command)
    assert error.value.code == "CLIENT_MESSAGE_ID_CONFLICT"

