from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, String
from sqlalchemy.dialects.mysql import MEDIUMTEXT
from sqlalchemy.orm import Mapped, mapped_column

from infr.config.base import Base


class SessionAuditEventModel(Base):
    __tablename__ = "session_audit_events"

    id: Mapped[str] = mapped_column(String(8), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(8), nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    actor: Mapped[str] = mapped_column(String(32), nullable=False, default="system", server_default="system")
    payload_json: Mapped[str] = mapped_column(MEDIUMTEXT, nullable=False)
    created_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)

    __table_args__ = (
        Index("idx_session_audit_events_session_time", "session_id", "created_time"),
    )
