from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from infr.config.base import Base


class ProjectModel(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(
        String(8), primary_key=True,
    )
    name: Mapped[str] = mapped_column(
        String(255), nullable=False,
    )
    dir_path: Mapped[str] = mapped_column(
        String(512), nullable=False,
    )
    agents_json: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, default=dict,
    )
    plugins_json: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, default=dict,
    )
    sort_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0",
    )
    created_time: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.now,
    )
    updated_time: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, default=datetime.now, onupdate=datetime.now,
    )
