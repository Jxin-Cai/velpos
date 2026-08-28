from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column

from infr.config.base import Base


class SkillEntryModel(Base):
    __tablename__ = "skill_entries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    category: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    tags: Mapped[list | None] = mapped_column(JSON, nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    repo_url: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    author: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    version: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    logo_emoji: Mapped[str] = mapped_column(String(16), nullable=False, default="🎯")
    created_by: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
