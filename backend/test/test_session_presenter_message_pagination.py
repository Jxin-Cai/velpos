from application.session.session_presenter import SessionPresenter
from domain.session.model.message import Message
from domain.session.model.message_type import MessageType


def _messages(count: int) -> list[Message]:
    return [
        Message.create(MessageType.ASSISTANT, {"text": f"message-{index}"})
        for index in range(count)
    ]


def test_returns_latest_page_when_before_is_omitted() -> None:
    # Arrange
    messages = _messages(5005)

    # Act
    page = SessionPresenter.message_page(messages)

    # Assert
    assert [message["_index"] for message in page["messages"]] == list(range(5, 5005))


def test_returns_previous_page_when_before_is_provided() -> None:
    # Arrange
    messages = _messages(10000)

    # Act
    page = SessionPresenter.message_page(messages, before=7500, limit=5000)

    # Assert
    assert page["message_window"] == {
        "start_index": 2500,
        "end_index": 7500,
        "total_count": 10000,
        "has_more": True,
    }


def test_returns_global_indices_when_user_markers_are_built() -> None:
    # Arrange
    messages = [
        Message.create(MessageType.SYSTEM, {"subtype": "init"}),
        Message.create(MessageType.USER, {"message_id": "prompt-1", "text": "  first   prompt  "}),
        Message.create(MessageType.ASSISTANT, {"text": "answer"}),
        Message.create(MessageType.USER, {"message_id": "prompt-2", "text": "second prompt"}),
    ]

    # Act
    markers = SessionPresenter.user_message_markers(messages)

    # Assert
    assert markers == [
        {"index": 1, "message_id": "prompt-1", "preview": "first prompt"},
        {"index": 3, "message_id": "prompt-2", "preview": "second prompt"},
    ]
