from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, SmallInteger, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from infr.config.base import Base


class ChannelProfileModel(Base):
    __tablename__ = "channel_profiles"
    __table_args__ = (
        Index("idx_channel_profiles_is_active", "is_active"),
    )

    profile_id: Mapped[str] = mapped_column(
        String(8), primary_key=True,
    )
    name: Mapped[str] = mapped_column(
        String(128), nullable=False,
    )
    host: Mapped[str] = mapped_column(
        String(512), nullable=False, default="", server_default="",
    )
    api_key: Mapped[str] = mapped_column(
        String(512), nullable=False, default="", server_default="",
    )
    auth_env_name: Mapped[str] = mapped_column(
        String(64), nullable=False, default="ANTHROPIC_API_KEY", server_default="ANTHROPIC_API_KEY",
    )
    model_config_json: Mapped[str] = mapped_column(
        "model_config", Text, nullable=False, default="{}",
    )
    is_active: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=0, server_default="0",
    )
    created_time: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.now,
    )
    updated_time: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.now, onupdate=datetime.now,
    )
