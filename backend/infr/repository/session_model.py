from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, String, SmallInteger
from sqlalchemy.dialects.mysql import MEDIUMTEXT, TEXT
from sqlalchemy.orm import Mapped, mapped_column

from infr.config.base import Base


class SessionModel(Base):
    __tablename__ = "sessions"

    session_id: Mapped[str] = mapped_column(
        String(8), primary_key=True,
    )
    project_id: Mapped[str] = mapped_column(
        String(8), nullable=False, default="", server_default="",
    )
    model: Mapped[str] = mapped_column(
        String(64), nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False,
    )
    messages: Mapped[str] = mapped_column(
        MEDIUMTEXT, nullable=False,
    )
    input_tokens: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0,
    )
    output_tokens: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0,
    )
    continue_conversation: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=0,
    )
    project_dir: Mapped[str] = mapped_column(
        String(512), nullable=False, default="", server_default="",
    )
    name: Mapped[str] = mapped_column(
        String(255), nullable=False, default="", server_default="",
    )
    sdk_session_id: Mapped[str] = mapped_column(
        String(64), nullable=False, default="", server_default="",
    )
    last_input_tokens: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default="0",
    )
    pending_request_context_json: Mapped[str] = mapped_column(
        MEDIUMTEXT, nullable=True,
    )
    queued_command_json: Mapped[str] = mapped_column(
        TEXT, nullable=True,
    )
    cancel_requested: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=0, server_default="0",
    )
    created_time: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.now,
    )
    updated_time: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.now, onupdate=datetime.now,
    )
