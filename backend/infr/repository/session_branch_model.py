from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, Integer, String
from sqlalchemy.dialects.mysql import MEDIUMTEXT
from sqlalchemy.orm import Mapped, mapped_column

from infr.config.base import Base


class SessionBranchModel(Base):
    __tablename__ = "session_branches"

    id: Mapped[str] = mapped_column(String(8), primary_key=True)
    source_session_id: Mapped[str] = mapped_column(String(8), nullable=False)
    branch_session_id: Mapped[str] = mapped_column(String(8), nullable=False)
    source_message_index: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False, default="", server_default="")
    root_session_id: Mapped[str] = mapped_column(String(8), nullable=False, default="", server_default="")
    group_id: Mapped[str] = mapped_column(String(8), nullable=False, default="", server_default="")
    sequence_no: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    worktree_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    worktree_path: Mapped[str] = mapped_column(String(500), nullable=False, default="", server_default="")
    base_branch: Mapped[str] = mapped_column(String(255), nullable=False, default="", server_default="")
    created_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)

    __table_args__ = (
        Index("idx_session_branches_source", "source_session_id", "created_time"),
        Index("idx_session_branches_branch", "branch_session_id"),
        Index("idx_session_branches_group", "group_id", "created_time"),
        Index("idx_session_branches_root", "root_session_id", "created_time"),
    )


class SessionSnapshotModel(Base):
    __tablename__ = "session_snapshots"

    id: Mapped[str] = mapped_column(String(8), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(8), nullable=False)
    message_index: Mapped[int] = mapped_column(Integer, nullable=False)
    messages_json: Mapped[str] = mapped_column(MEDIUMTEXT, nullable=False)
    created_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)

    __table_args__ = (
        Index("idx_session_snapshots_session", "session_id", "message_index"),
    )
