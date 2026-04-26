from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.dialects.mysql import MEDIUMTEXT
from sqlalchemy.orm import Mapped, mapped_column

from infr.config.base import Base


class EvolutionProposalModel(Base):
    __tablename__ = "evolution_proposals"

    id: Mapped[str] = mapped_column(String(8), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(8), nullable=False, default="", server_default="")
    source_session_id: Mapped[str] = mapped_column(String(8), nullable=False, default="", server_default="")
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    extracted_lessons_json: Mapped[str] = mapped_column(MEDIUMTEXT, nullable=False)
    proposed_claude_md_revision_id: Mapped[str] = mapped_column(String(8), nullable=False, default="", server_default="")
    created_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)
    updated_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)
