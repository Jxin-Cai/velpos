from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.mysql import MEDIUMTEXT
from sqlalchemy.orm import Mapped, mapped_column

from infr.config.base import Base


class SessionTimelineEventModel(Base):
    __tablename__ = "session_timeline_events"

    id: Mapped[str] = mapped_column(String(12), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(8), nullable=False)
    run_id: Mapped[str] = mapped_column(String(32), nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    payload_json: Mapped[str] = mapped_column(MEDIUMTEXT, nullable=False)
    started_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)
    ended_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    duration_ms: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default="0")
    created_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)

    __table_args__ = (
        UniqueConstraint("session_id", "run_id", "seq", name="uq_session_timeline_events_run_seq"),
        Index("idx_session_timeline_events_session_time", "session_id", "created_time"),
        Index("idx_session_timeline_events_session_run", "session_id", "run_id", "seq"),
        Index("idx_session_timeline_events_type", "session_id", "event_type", "created_time"),
    )
