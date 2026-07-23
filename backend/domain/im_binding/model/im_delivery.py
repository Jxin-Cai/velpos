from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any


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


@dataclass
class ImInboxEvent:
    id: int
    channel_id: str
    channel_type: str
    binding_id: str
    session_id: str
    external_message_id: str
    content: str
    sender_id: str = ""
    group_id: str = ""
    status: ImInboxStatus = ImInboxStatus.RECEIVED
    attempt_count: int = 0
    next_attempt_at: datetime = field(default_factory=datetime.now)
    lease_until: datetime | None = None
    error_message: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

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


@dataclass
class ImOutboxMessage:
    id: int
    session_id: str
    binding_id: str
    channel_id: str
    channel_type: str
    content: str
    deduplication_key: str
    reply_context: dict[str, Any] = field(default_factory=dict)
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
