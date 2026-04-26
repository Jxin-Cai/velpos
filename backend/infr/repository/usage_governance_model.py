from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, Index, String, BigInteger
from sqlalchemy.orm import Mapped, mapped_column

from infr.config.base import Base


class UsageLedgerModel(Base):
    __tablename__ = "usage_ledgers"

    id: Mapped[str] = mapped_column(String(8), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(8), nullable=False)
    project_id: Mapped[str] = mapped_column(String(8), nullable=False, default="", server_default="")
    model: Mapped[str] = mapped_column(String(100), nullable=False, default="", server_default="")
    input_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default="0")
    output_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default="0")
    cache_read_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default="0")
    cache_creation_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default="0")
    estimated_cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0, server_default="0")
    created_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)

    __table_args__ = (
        Index("idx_usage_ledgers_session_time", "session_id", "created_time"),
        Index("idx_usage_ledgers_project_time", "project_id", "created_time"),
    )


class BudgetPolicyModel(Base):
    __tablename__ = "budget_policies"

    id: Mapped[str] = mapped_column(String(8), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(8), nullable=False, unique=True)
    daily_token_limit: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default="0")
    daily_cost_limit_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0, server_default="0")
    on_exceed: Mapped[str] = mapped_column(String(16), nullable=False, default="warn", server_default="warn")
    updated_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)
