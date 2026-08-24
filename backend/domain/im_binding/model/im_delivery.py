from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

from domain.im_binding.model.channel_route import ChannelRoute


class ImInboxStatus(str, Enum):
    RECEIVED = "received"
    PROCESSING = "processing"
    RETRY = "retry"
    PROCESSED = "processed"
    DEAD = "dead"


class ImOutboxStatus(str, Enum):
    PENDING = "pending"
    SENDING = "sending"
    RETRY = "retry"
    SENT = "sent"
    CANCELLED = "cancelled"
    DEAD = "dead"


class ImDeliveryKind(str, Enum):
    """投递方向 — 监控与重投 API 用它区分两条队列."""

    INBOX = "inbox"
    OUTBOX = "outbox"


#: 入站队列中"尚未成功"的状态 — 监控视图关注的对象.
INBOX_UNSETTLED_STATUSES: frozenset[ImInboxStatus] = frozenset(
    {
        ImInboxStatus.RECEIVED,
        ImInboxStatus.PROCESSING,
        ImInboxStatus.RETRY,
        ImInboxStatus.DEAD,
    }
)

#: 出站队列中"尚未成功"的状态 — 监控视图关注的对象.
OUTBOX_UNSETTLED_STATUSES: frozenset[ImOutboxStatus] = frozenset(
    {
        ImOutboxStatus.PENDING,
        ImOutboxStatus.SENDING,
        ImOutboxStatus.RETRY,
        ImOutboxStatus.CANCELLED,
        ImOutboxStatus.DEAD,
    }
)


@dataclass
class ImInboxEvent:
    id: int
    channel_id: str
    channel_type: str
    binding_id: str
    session_id: str
    external_message_id: str
    content: str
    route: ChannelRoute = field(default_factory=ChannelRoute)
    attachments: list[dict[str, Any]] = field(default_factory=list)
    status: ImInboxStatus = ImInboxStatus.RECEIVED
    attempt_count: int = 0
    next_attempt_at: datetime = field(default_factory=datetime.now)
    lease_until: datetime | None = None
    error_message: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    @property
    def sender_id(self) -> str:
        return self.route.sender_id

    @property
    def group_id(self) -> str:
        return self.route.group_id

    def claim(self, lease_seconds: int) -> None:
        now = datetime.now()
        self.status = ImInboxStatus.PROCESSING
        self.attempt_count += 1
        self.lease_until = now + timedelta(seconds=lease_seconds)
        self.updated_at = now

    def mark_processed(self) -> None:
        self.status = ImInboxStatus.PROCESSED
        self.lease_until = None
        self.error_message = ""
        self.updated_at = datetime.now()

    def mark_retry(self, error_message: str, delay_seconds: int) -> None:
        now = datetime.now()
        self.status = ImInboxStatus.RETRY
        self.lease_until = None
        self.next_attempt_at = now + timedelta(seconds=delay_seconds)
        self.error_message = error_message[:1000]
        self.updated_at = now

    def mark_dead(self, error_message: str) -> None:
        self.status = ImInboxStatus.DEAD
        self.lease_until = None
        self.error_message = error_message[:1000]
        self.updated_at = datetime.now()

    def requeue(self) -> None:
        """把死信重新放回队列, 尝试计数归零.

        只允许从 DEAD 状态发起: 其他状态要么还在队列里, 要么已成功,
        重投都会造成重复处理。
        """
        if self.status is not ImInboxStatus.DEAD:
            raise ValueError(
                f"Only dead inbox events can be requeued, "
                f"current status: {self.status.value}"
            )
        now = datetime.now()
        self.status = ImInboxStatus.RETRY
        self.attempt_count = 0
        self.next_attempt_at = now
        self.lease_until = None
        self.updated_at = now


@dataclass
class ImOutboxMessage:
    id: int
    session_id: str
    binding_id: str
    channel_id: str
    channel_type: str
    content: str
    deduplication_key: str
    attachments: list[dict[str, Any]] = field(default_factory=list)
    route: ChannelRoute = field(default_factory=ChannelRoute)
    status: ImOutboxStatus = ImOutboxStatus.PENDING
    attempt_count: int = 0
    next_attempt_at: datetime = field(default_factory=datetime.now)
    lease_until: datetime | None = None
    error_message: str = ""
    external_message_id: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    def claim(self, lease_seconds: int) -> None:
        now = datetime.now()
        self.status = ImOutboxStatus.SENDING
        self.attempt_count += 1
        self.lease_until = now + timedelta(seconds=lease_seconds)
        self.updated_at = now

    def mark_sent(self, external_message_id: str = "") -> None:
        self.status = ImOutboxStatus.SENT
        self.lease_until = None
        self.error_message = ""
        self.external_message_id = external_message_id
        self.updated_at = datetime.now()

    def mark_retry(self, error_message: str, delay_seconds: int) -> None:
        now = datetime.now()
        self.status = ImOutboxStatus.RETRY
        self.lease_until = None
        self.next_attempt_at = now + timedelta(seconds=delay_seconds)
        self.error_message = error_message[:1000]
        self.updated_at = now

    def mark_cancelled(self, error_message: str) -> None:
        self.status = ImOutboxStatus.CANCELLED
        self.lease_until = None
        self.error_message = error_message[:1000]
        self.updated_at = datetime.now()

    def mark_dead(self, error_message: str) -> None:
        self.status = ImOutboxStatus.DEAD
        self.lease_until = None
        self.error_message = error_message[:1000]
        self.updated_at = datetime.now()

    def requeue(self) -> None:
        """把最终失败的消息重新放回队列, 尝试计数归零.

        DEAD 与 CANCELLED 均可重投: CANCELLED 多因凭证失效或换绑而取消,
        用户修复渠道后重投是合理动作; 队列 worker 会重新校验绑定,
        条件仍不满足时消息会被再次取消, 不会误发。
        """
        if self.status not in (ImOutboxStatus.DEAD, ImOutboxStatus.CANCELLED):
            raise ValueError(
                f"Only dead or cancelled outbox messages can be requeued, "
                f"current status: {self.status.value}"
            )
        now = datetime.now()
        self.status = ImOutboxStatus.RETRY
        self.attempt_count = 0
        self.next_attempt_at = now
        self.lease_until = None
        self.updated_at = now
