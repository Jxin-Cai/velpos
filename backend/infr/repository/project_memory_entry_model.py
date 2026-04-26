from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, String
from sqlalchemy.dialects.mysql import MEDIUMTEXT
from sqlalchemy.orm import Mapped, mapped_column

from infr.config.base import Base


class ProjectMemoryEntryModel(Base):
    __tablename__ = "project_memory_entries"

    id: Mapped[str] = mapped_column(String(8), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(8), nullable=False)
    memory_type: Mapped[str] = mapped_column(String(32), nullable=False, default="note", server_default="note")
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(MEDIUMTEXT, nullable=False)
    source_session_id: Mapped[str] = mapped_column(String(8), nullable=False, default="", server_default="")
    source_message_id: Mapped[str] = mapped_column(String(64), nullable=False, default="", server_default="")
    visibility: Mapped[str] = mapped_column(String(32), nullable=False, default="project", server_default="project")
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="active", server_default="active")
    created_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)
    updated_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

    __table_args__ = (
        Index("idx_project_memory_entries_project_state", "project_id", "state", "updated_time"),
    )
