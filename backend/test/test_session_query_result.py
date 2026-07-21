from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from domain.session.model.message import Message
from domain.session.model.message_type import MessageType
from domain.session.model.session import Session
from application.session.session_query_engine import SessionQueryEngine


def test_result_failure_reason_when_claude_returns_error() -> None:
    # Arrange
    session = Session.create()
    session.add_message(
        Message.create(
            MessageType.RESULT,
            {"is_error": True, "text": "MODEL_NOT_ALLOWED"},
        )
    )

    # Act
    reason = SessionQueryEngine._result_failure_reason(session)

    # Assert
    assert reason == "MODEL_NOT_ALLOWED"


def test_result_failure_reason_empty_when_claude_returns_success() -> None:
    # Arrange
    session = Session.create()
    session.add_message(
        Message.create(
            MessageType.RESULT,
            {"is_error": False, "text": "done"},
        )
    )

    # Act
    reason = SessionQueryEngine._result_failure_reason(session)

    # Assert
    assert reason == ""


def test_transient_result_error_detected_when_upstream_returns_503() -> None:
    # Arrange
    reason = (
        'API Error: 503 CHANNEL_UNAVAILABLE: Upstream returned HTTP 503: '
        '{"error":{"message":"Service temporarily unavailable"}}'
    )

    # Act
    is_transient = SessionQueryEngine._is_transient_result_error(reason)

    # Assert
    assert is_transient is True


def test_transient_result_error_not_detected_when_model_is_not_allowed() -> None:
    # Arrange
    reason = "MODEL_NOT_ALLOWED"

    # Act
    is_transient = SessionQueryEngine._is_transient_result_error(reason)

    # Assert
    assert is_transient is False


@pytest.mark.asyncio
async def test_transient_result_is_retried_when_next_attempt_succeeds(
    monkeypatch,
) -> None:
    # Arrange
    monkeypatch.setenv("CLAUDE_TRANSIENT_RESULT_RETRIES", "2")
    monkeypatch.setenv("CLAUDE_TRANSIENT_RETRY_BASE_DELAY_SECONDS", "0")
    session = Session.create()
    session.add_message(
        Message.create(
            MessageType.RESULT,
            {"is_error": True, "text": "503 CHANNEL_UNAVAILABLE"},
        )
    )

    async def consume_success(*_args) -> bool:
        session.add_message(
            Message.create(
                MessageType.RESULT,
                {"is_error": False, "text": "done"},
            )
        )
        return True

    engine = SessionQueryEngine(
        session_repository=Mock(),
        claude_agent_gateway=SimpleNamespace(send_query=Mock(return_value=object())),
        connection_manager=SimpleNamespace(broadcast=AsyncMock()),
        recorder=SimpleNamespace(
            record_audit_event=AsyncMock(),
            record_timeline_event=AsyncMock(),
        ),
        stream_consumer=SimpleNamespace(consume=AsyncMock(side_effect=consume_success)),
        save_session_fn=AsyncMock(),
        reconnect_db_session_fn=AsyncMock(),
        accept_or_reject_sdk_session_id_fn=AsyncMock(),
        resolve_resume_sdk_session_id_fn=AsyncMock(),
        refresh_context_usage_fn=AsyncMock(),
    )
    ctx = SimpleNamespace(
        session=session,
        command=SimpleNamespace(session_id=session.session_id),
        run_id="run-1",
        actual_prompt="retry me",
    )

    # Act
    await engine._retry_transient_result(ctx, got_result=True)

    # Assert
    assert engine._result_failure_reason(session) == ""


def test_stream_end_result_is_success_when_assistant_output_exists() -> None:
    # Arrange
    session = Session.create()
    session.add_message(
        Message.create(
            MessageType.ASSISTANT,
            {"blocks": [{"type": "text", "text": "Completed the task."}]},
        )
    )

    # Act
    result = SessionQueryEngine._build_stream_end_result(session, auto_continue_count=1)

    # Assert
    assert result.content["is_error"] is False
    assert result.content["stop_reason"] == "stream_ended_after_output"


def test_stream_end_result_is_failure_when_assistant_output_is_missing() -> None:
    # Arrange
    session = Session.create()

    # Act
    result = SessionQueryEngine._build_stream_end_result(session, auto_continue_count=1)

    # Assert
    assert result.content["is_error"] is True
    assert result.content["text"] == "Agent stream ended without a successful result."
