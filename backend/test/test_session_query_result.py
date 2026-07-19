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
