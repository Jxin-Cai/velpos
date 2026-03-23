from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from infr.config.base import Base


class ChannelInitModel(Base):
    __tablename__ = "channel_inits"
    __table_args__ = (
        Index("ix_channel_inits_type", "channel_type"),
    )

    id: Mapped[str] = mapped_column(
        String(8), primary_key=True,
    )
    channel_type: Mapped[str] = mapped_column(
        String(32), nullable=False,
    )
    name: Mapped[str] = mapped_column(
        String(128), nullable=False, default="",
    )
    init_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="not_initialized",
    )
    config_json: Mapped[str] = mapped_column(
        String(4096), nullable=False, default="{}",
    )
    error_message: Mapped[str] = mapped_column(
        String(1024), nullable=False, default="",
    )
    created_time: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.now,
    )
    updated_time: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.now, onupdate=datetime.now,
    )
