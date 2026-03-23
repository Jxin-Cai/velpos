from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from infr.config.base import Base


class ImBindingModel(Base):
    __tablename__ = "im_bindings"
    __table_args__ = (
        UniqueConstraint("channel_id", name="uq_im_bindings_channel_id"),
        UniqueConstraint("session_id", name="uq_im_bindings_session"),
    )

    id: Mapped[str] = mapped_column(
        String(8), primary_key=True,
    )
    session_id: Mapped[str] = mapped_column(
        String(8), nullable=False,
    )
    channel_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default="openim",
    )
    channel_id: Mapped[str] = mapped_column(
        String(8), nullable=False, default="",
    )
    channel_address: Mapped[str] = mapped_column(
        String(256), nullable=False, default="",
    )
    config_json: Mapped[str] = mapped_column(
        String(2048), nullable=False, default="{}",
    )
    im_user_id: Mapped[str] = mapped_column(
        String(64), nullable=False,
    )
    im_token: Mapped[str] = mapped_column(
        String(512), nullable=False, default="",
    )
    binding_status: Mapped[str] = mapped_column(
        String(16), nullable=False,
    )
    friend_user_id: Mapped[str] = mapped_column(
        String(64), nullable=False, default="",
    )
    qr_code_data: Mapped[str] = mapped_column(
        String(512), nullable=False, default="",
    )
    created_time: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.now,
    )
    updated_time: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.now, onupdate=datetime.now,
    )
