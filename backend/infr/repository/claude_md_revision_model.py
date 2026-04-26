from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String
from sqlalchemy.dialects.mysql import MEDIUMTEXT
from sqlalchemy.orm import Mapped, mapped_column

from infr.config.base import Base


class ClaudeMdRevisionModel(Base):
    __tablename__ = "claude_md_revisions"

    id: Mapped[str] = mapped_column(String(8), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(8), nullable=False)
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(MEDIUMTEXT, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    base_revision_id: Mapped[str] = mapped_column(String(8), nullable=False, default="", server_default="")
    base_file_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="", server_default="")
    created_by: Mapped[str] = mapped_column(String(32), nullable=False, default="user", server_default="user")
    created_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)
    proposed_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    approved_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    applied_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    rejected_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    reject_reason: Mapped[str] = mapped_column(String(512), nullable=False, default="", server_default="")

    __table_args__ = (
        Index("idx_claude_md_revisions_project_version", "project_id", "version_no"),
        Index("idx_claude_md_revisions_project_state", "project_id", "state"),
    )


class ClaudeMdRevisionEventModel(Base):
    __tablename__ = "claude_md_revision_events"

    id: Mapped[str] = mapped_column(String(8), primary_key=True)
    revision_id: Mapped[str] = mapped_column(String(8), nullable=False)
    from_state: Mapped[str] = mapped_column(String(16), nullable=False)
    to_state: Mapped[str] = mapped_column(String(16), nullable=False)
    payload_json: Mapped[str] = mapped_column(MEDIUMTEXT, nullable=False)
    created_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)

    __table_args__ = (
        Index("idx_claude_md_revision_events_revision_time", "revision_id", "created_time"),
    )
