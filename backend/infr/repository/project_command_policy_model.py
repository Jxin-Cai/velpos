from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import DateTime, Index, String, UniqueConstraint
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from infr.config.base import Base


class ProjectCommandPolicyModel(Base):
    __tablename__ = "project_command_policies"

    id: Mapped[str] = mapped_column(String(8), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(8), nullable=False)
    command_name: Mapped[str] = mapped_column(String(128), nullable=False)
    command_type: Mapped[str] = mapped_column(String(32), nullable=False, default="unknown", server_default="unknown")
    enabled: Mapped[int] = mapped_column(nullable=False, default=1, server_default="1")
    visible: Mapped[int] = mapped_column(nullable=False, default=1, server_default="1")
    default_args_json: Mapped[dict | list | str | None] = mapped_column(JSON, nullable=True)
    updated_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

    __table_args__ = (
        UniqueConstraint("project_id", "command_name", "command_type", name="uq_project_command_policy"),
        Index("idx_project_command_policies_project", "project_id"),
    )

    @property
    def default_args_dict(self) -> dict:
        value = self.default_args_json
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
                return parsed if isinstance(parsed, dict) else {}
            except json.JSONDecodeError:
                return {}
        return {}
