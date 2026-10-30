from collections.abc import Callable
from typing import Any

import pytest

from application.session.session_presenter import SessionPresenter
from domain.session.model.session import Session
from ohs.assembler.session_assembler import SessionAssembler


@pytest.fixture(params=[SessionAssembler.to_summary, SessionPresenter.session_to_dict])
def serialize(request) -> Callable[[Session], dict[str, Any]]:
    return request.param


@pytest.mark.parametrize(
    ("pending_request", "expected"),
    [
        (None, None),
        (
            {"tool_name": "AskUserQuestion", "questions": [{"question": "Which branch?"}]},
            {
                "interaction_type": "user_choice",
                "tool_name": "AskUserQuestion",
                "questions": [{"question": "Which branch?"}],
            },
        ),
        (
            {"tool_name": "Bash", "tool_input": {"command": "git status"}},
            {
                "interaction_type": "permission",
                "tool_name": "Bash",
                "tool_input": {"command": "git status"},
            },
        ),
        (
            {"tool_name": "Read"},
            {"interaction_type": "permission", "tool_name": "Read", "tool_input": ""},
        ),
    ],
)
def test_preserves_pending_request_when_session_is_serialized(
    serialize, pending_request, expected,
) -> None:
    # Arrange
    session = Session.create()
    session.update_pending_request_context(pending_request)

    # Act
    summary = serialize(session)

    # Assert
    assert summary["recovery"]["pending_request"] == expected


def test_preserves_queued_message_metadata_when_command_is_pending(serialize) -> None:
    # Arrange
    session = Session.create()
    session.update_queued_command(
        "continue",
        image_paths=["/tmp/image.png"],
        attachments=[{"filename": "notes.txt"}, {"filename": "report.pdf"}],
        client_message_id="message-1",
    )

    # Act
    summary = serialize(session)

    # Assert
    assert summary["recovery"]["queued_command"] == {
        "message_id": "message-1",
        "prompt": "continue",
        "image_count": 1,
        "attachment_count": 2,
    }


def test_returns_empty_recovery_when_session_has_no_pending_work(serialize) -> None:
    # Arrange
    session = Session.create()

    # Act
    summary = serialize(session)

    # Assert
    assert summary["recovery"] == {
        "pending_request": None,
        "queued_command": None,
        "cancel_requested": False,
    }


def test_preserves_cancel_request_when_session_is_serialized(serialize) -> None:
    # Arrange
    session = Session.create()
    session.mark_cancel_requested()

    # Act
    summary = serialize(session)

    # Assert
    assert summary["recovery"]["cancel_requested"] is True


@pytest.mark.parametrize(
    ("sdk_session_id", "expected"),
    [("", ""), ("sdk-session-1", "sdk-session-1"), ("fork:internal-session", "")],
)
def test_exposes_public_sdk_id_when_session_is_serialized(
    serialize, sdk_session_id, expected,
) -> None:
    # Arrange
    session = Session.create()
    session.update_sdk_session_id(sdk_session_id)

    # Act
    summary = serialize(session)

    # Assert
    assert summary["sdk_session_id"] == expected


@pytest.mark.parametrize(("field", "expected"), [("git_branch", "feature"), ("trace_id", "trace-1")])
def test_preserves_adapter_metadata_when_session_summary_is_built(field, expected) -> None:
    # Arrange
    session = Session.create(trace_id="trace-1")

    # Act
    summary = SessionAssembler.to_summary(session, git_branch="feature")

    # Assert
    assert summary[field] == expected
