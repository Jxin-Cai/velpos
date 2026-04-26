from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, BigInteger, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from infr.config.base import Base


class AttachmentModel(Base):
    __tablename__ = "attachments"

    id: Mapped[str] = mapped_column(String(8), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(8), nullable=False, default="", server_default="")
    session_id: Mapped[str] = mapped_column(String(8), nullable=False, default="", server_default="")
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(128), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    storage_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)


class MessageAttachmentModel(Base):
    __tablename__ = "message_attachments"
    __table_args__ = (
        UniqueConstraint("message_id", "attachment_id", name="uq_message_attachment"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    message_id: Mapped[str] = mapped_column(String(32), nullable=False)
    attachment_id: Mapped[str] = mapped_column(String(8), nullable=False)
