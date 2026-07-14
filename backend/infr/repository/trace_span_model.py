from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.mysql import MEDIUMTEXT
from sqlalchemy.orm import Mapped, mapped_column

from infr.config.base import Base


class TraceSpanModel(Base):
    __tablename__ = "trace_spans"

    id: Mapped[str] = mapped_column(String(16), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        String(8),
        ForeignKey("sessions.session_id", ondelete="CASCADE"),
        nullable=False,
    )
    run_id: Mapped[str] = mapped_column(String(32), nullable=False)
    parent_span_id: Mapped[str | None] = mapped_column(String(16), nullable=True)
    span_type: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    agent_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    tool_use_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    input_preview: Mapped[str | None] = mapped_column(MEDIUMTEXT, nullable=True)
    output_preview: Mapped[str | None] = mapped_column(MEDIUMTEXT, nullable=True)
    metadata_json: Mapped[str] = mapped_column(MEDIUMTEXT, nullable=False, default="{}")
    started_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)
    ended_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    duration_ms: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default="0")
    created_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)

    __table_args__ = (
        Index("idx_trace_spans_session_run", "session_id", "run_id", "started_time"),
        Index("idx_trace_spans_tool_use", "session_id", "tool_use_id"),
        Index("idx_trace_spans_agent", "session_id", "agent_id"),
        Index("idx_trace_spans_parent", "parent_span_id"),
    )
