from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from domain.session.model.message_type import MessageType


@dataclass(frozen=True)
class Message:
    message_type: MessageType
    content: dict[str, Any]
    #: 消息落地时间; 历史数据可能缺失, 展示层需容忍 None.
    created_at: datetime | None = None

    @classmethod
    def create(cls, message_type: MessageType, content: dict[str, Any]) -> Message:
        """Create a Message value object stamped with the current time.

        Validates that message_type and content are not None.
        """
        if message_type is None:
            raise ValueError("message_type must not be None")
        if content is None:
            raise ValueError("content must not be None")
        return cls(
            message_type=message_type,
            content=content,
            created_at=datetime.now(),
        )
