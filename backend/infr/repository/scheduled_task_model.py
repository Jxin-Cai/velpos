from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, String, SmallInteger
from sqlalchemy.dialects.mysql import MEDIUMTEXT
from sqlalchemy.orm import Mapped, mapped_column

from infr.config.base import Base


class ScheduledTaskModel(Base):
    __tablename__ = "scheduled_tasks"

    id: Mapped[str] = mapped_column(String(8), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(8), nullable=False, default="", server_default="")
    session_id: Mapped[str] = mapped_column(String(8), nullable=False, default="", server_default="")
    channel_id: Mapped[str] = mapped_column(String(8), nullable=False, default="", server_default="")
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    prompt: Mapped[str] = mapped_column(MEDIUMTEXT, nullable=False)
    cron_expr: Mapped[str] = mapped_column(String(64), nullable=False)
    enabled: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1, server_default="1")
    auto_unbind_after_run: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1, server_default="1")
    delete_session_on_success: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0, server_default="0")
    next_run_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)

    __table_args__ = (
        Index("idx_scheduled_tasks_next", "enabled", "next_run_time"),
        Index("idx_scheduled_tasks_project", "project_id"),
        Index("idx_scheduled_tasks_channel", "channel_id"),
    )


class ScheduledTaskRunModel(Base):
    __tablename__ = "scheduled_task_runs"

    id: Mapped[str] = mapped_column(String(8), primary_key=True)
    task_id: Mapped[str] = mapped_column(String(8), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    started_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)
    ended_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    result_session_id: Mapped[str] = mapped_column(String(8), nullable=False, default="", server_default="")
    error_message: Mapped[str] = mapped_column(String(500), nullable=False, default="", server_default="")

    __table_args__ = (
        Index("idx_scheduled_task_runs_task_time", "task_id", "started_time"),
    )
