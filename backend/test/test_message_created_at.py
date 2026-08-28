"""消息时间标记 — 用户消息与 AI 结果的时间在持久化与展示层透出."""

from __future__ import annotations

from datetime import datetime

from application.session.session_presenter import SessionPresenter
from domain.session.model.message import Message
from domain.session.model.message_type import MessageType
from infr.repository.session_repository_impl import SessionRepositoryImpl


def test_stamps_created_at_when_message_is_created():
    # Arrange / Act
    message = Message.create(MessageType.USER, {"text": "你好"})

    # Assert
    assert message.created_at is not None
    assert (datetime.now() - message.created_at).total_seconds() < 5


def test_preserves_created_at_when_messages_round_trip_through_storage():
    # Arrange
    message = Message.create(MessageType.ASSISTANT, {"blocks": []})

    # Act
    serialized = SessionRepositoryImpl._serialize_messages([message])
    restored = SessionRepositoryImpl._deserialize_messages(serialized)

    # Assert
    assert restored[0].created_at == message.created_at


def test_returns_none_created_at_when_stored_message_predates_timestamps():
    # Arrange — 旧数据没有 created_at 字段
    legacy_json = '[{"type": "user", "content": {"text": "旧消息"}}]'

    # Act
    restored = SessionRepositoryImpl._deserialize_messages(legacy_json)

    # Assert
    assert restored[0].created_at is None


def test_exposes_created_at_when_message_is_presented():
    # Arrange
    message = Message.create(MessageType.RESULT, {"is_error": False})

    # Act
    payload = SessionPresenter.message_to_dict(message)

    # Assert
    assert payload["created_at"] == message.created_at.isoformat()


def test_exposes_null_created_at_when_message_has_no_timestamp():
    # Arrange
    message = Message(message_type=MessageType.USER, content={"text": "旧消息"})

    # Act
    payload = SessionPresenter.message_to_dict(message)

    # Assert
    assert payload["created_at"] is None
