from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, String
from sqlalchemy.dialects.mysql import MEDIUMTEXT
from sqlalchemy.orm import Mapped, mapped_column

from infr.config.base import Base


class SessionRunStepModel(Base):
    __tablename__ = "session_run_steps"

    id: Mapped[str] = mapped_column(String(8), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(8), nullable=False)
    run_id: Mapped[str] = mapped_column(String(8), nullable=False)
    step_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    payload_json: Mapped[str] = mapped_column(MEDIUMTEXT, nullable=False)
    started_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)
    ended_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    duration_ms: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default="0")

    __table_args__ = (
        Index("idx_session_run_steps_session_run", "session_id", "run_id", "started_time"),
        Index("idx_session_run_steps_session_time", "session_id", "started_time"),
    )
