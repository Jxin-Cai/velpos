from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.mysql import MEDIUMTEXT
from sqlalchemy.orm import Mapped, mapped_column

from infr.config.base import Base


class ExecutionLedgerEventModel(Base):
    __tablename__ = "execution_events"

    position: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(String(32), nullable=False)
    session_id: Mapped[str] = mapped_column(
        String(8),
        ForeignKey("sessions.session_id", ondelete="CASCADE"),
        nullable=False,
    )
    run_id: Mapped[str] = mapped_column(String(32), nullable=False)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    span_id: Mapped[str] = mapped_column(String(16), nullable=False)
    parent_span_id: Mapped[str | None] = mapped_column(String(16), nullable=True)
    span_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    agent_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    tool_use_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    causation_event_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    event_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    ingested_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    payload_json: Mapped[str] = mapped_column(MEDIUMTEXT, nullable=False, default="{}")

    __table_args__ = (
        UniqueConstraint("event_id", name="uq_execution_events_event_id"),
        Index("idx_execution_events_session_run_position", "session_id", "run_id", "position"),
        Index("idx_execution_events_span_position", "span_id", "position"),
    )
