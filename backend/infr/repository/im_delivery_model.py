from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from infr.config.base import Base


class ImInboxEventModel(Base):
    __tablename__ = "im_inbox_events"
    __table_args__ = (
        UniqueConstraint(
            "channel_id",
            "external_message_id",
            name="uq_im_inbox_channel_message",
        ),
        Index("idx_im_inbox_processable", "status", "next_attempt_at", "lease_until"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    channel_id: Mapped[str] = mapped_column(String(36), nullable=False)
    channel_type: Mapped[str] = mapped_column(String(32), nullable=False)
    binding_id: Mapped[str] = mapped_column(String(8), nullable=False)
    session_id: Mapped[str] = mapped_column(String(8), nullable=False)
    external_message_id: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    sender_id: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    group_id: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    error_message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.now,
        onupdate=datetime.now,
    )


class ImOutboxMessageModel(Base):
    __tablename__ = "im_outbox_messages"
    __table_args__ = (
        UniqueConstraint("deduplication_key", name="uq_im_outbox_deduplication_key"),
        Index("idx_im_outbox_processable", "status", "next_attempt_at", "lease_until"),
        Index("idx_im_outbox_session_order", "session_id", "id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(8), nullable=False)
    binding_id: Mapped[str] = mapped_column(String(8), nullable=False)
    channel_id: Mapped[str] = mapped_column(String(36), nullable=False)
    channel_type: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    deduplication_key: Mapped[str] = mapped_column(String(255), nullable=False)
    reply_context_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    error_message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    external_message_id: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.now,
        onupdate=datetime.now,
    )
