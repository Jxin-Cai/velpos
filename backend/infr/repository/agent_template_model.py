from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column

from infr.config.base import Base


class AgentTemplateModel(Base):
    __tablename__ = "agent_templates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name_en: Mapped[str] = mapped_column(String(128), nullable=False)
    name_zh: Mapped[str] = mapped_column(String(128), nullable=False)
    description_en: Mapped[str] = mapped_column(Text, nullable=False, default="")
    description_zh: Mapped[str] = mapped_column(Text, nullable=False, default="")
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    emoji: Mapped[str] = mapped_column(String(16), nullable=False, default="🤖")
    color: Mapped[str] = mapped_column(String(32), nullable=False, default="#6366f1")
    prompt_en: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_zh: Mapped[str] = mapped_column(Text, nullable=False)
    plugins_config: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_by: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
