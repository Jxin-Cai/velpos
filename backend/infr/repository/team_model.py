from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.engine.interfaces import Dialect
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator

from infr.config.base import Base


class UTCDateTime(TypeDecorator[datetime]):
    impl = DateTime
    cache_ok = True

    def process_bind_param(
        self,
        value: datetime | None,
        dialect: Dialect,
    ) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value
        return value.astimezone(timezone.utc).replace(tzinfo=None)

    def process_result_value(
        self,
        value: datetime | None,
        dialect: Dialect,
    ) -> datetime | None:
        if value is None or value.tzinfo is not None:
            return value
        return value.replace(tzinfo=timezone.utc)


class TeamModel(Base):
    __tablename__ = "teams"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(8), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_time: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    updated_time: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    agent_slots: Mapped[list[AgentSlotModel]] = relationship(
        back_populates="team",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="AgentSlotModel.created_time",
    )

    __table_args__ = (
        UniqueConstraint("project_id", name="uq_teams_project_id"),
        Index("idx_teams_updated", "updated_time"),
    )


class AgentSlotModel(Base):
    __tablename__ = "team_agent_slots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    team_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("teams.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(Text, nullable=False)
    workspace_ref: Mapped[str] = mapped_column(String(512), nullable=False)
    availability: Mapped[str] = mapped_column(String(16), nullable=False, default="available", server_default="available")
    created_time: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    team: Mapped[TeamModel] = relationship(back_populates="agent_slots")

    __table_args__ = (
        UniqueConstraint("team_id", "name", name="uq_team_agent_slots_name"),
        UniqueConstraint("team_id", "workspace_ref", name="uq_team_agent_slots_workspace"),
        Index("idx_team_agent_slots_team", "team_id", "created_time"),
    )


class WishCardModel(Base):
    __tablename__ = "wish_cards"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    team_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("teams.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(
        Text, nullable=False, default="", server_default=""
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    assigned_agent_slot_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("team_agent_slots.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_time: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    updated_time: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    executions: Mapped[list[CardExecutionModel]] = relationship(
        back_populates="card",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="CardExecutionModel.created_time",
    )

    __table_args__ = (
        Index("idx_wish_cards_team_status", "team_id", "status", "updated_time"),
        Index("idx_wish_cards_assignee", "assigned_agent_slot_id"),
    )


class CardExecutionModel(Base):
    __tablename__ = "card_executions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    card_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("wish_cards.id", ondelete="CASCADE"), nullable=False
    )
    agent_slot_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("team_agent_slots.id", ondelete="RESTRICT"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_time: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    started_time: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    ended_time: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    session_id: Mapped[str | None] = mapped_column(String(8), nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    card: Mapped[WishCardModel] = relationship(back_populates="executions")

    __table_args__ = (
        UniqueConstraint("card_id", "idempotency_key", name="uq_card_executions_idempotency"),
        Index("idx_card_executions_card_time", "card_id", "created_time"),
        Index("idx_card_executions_slot_status", "agent_slot_id", "status"),
    )


class CardHandoffModel(Base):
    __tablename__ = "card_handoffs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    team_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("teams.id", ondelete="CASCADE"), nullable=False
    )
    card_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("wish_cards.id", ondelete="CASCADE"), nullable=False
    )
    source_execution_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("card_executions.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_agent_slot_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("team_agent_slots.id", ondelete="RESTRICT"),
        nullable=False,
    )
    target_agent_slot_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("team_agent_slots.id", ondelete="RESTRICT"),
        nullable=False,
    )
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    created_time: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    resolved_time: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    artifacts: Mapped[list[HandoffArtifactModel]] = relationship(
        back_populates="handoff",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="HandoffArtifactModel.created_time",
    )

    __table_args__ = (
        Index("idx_card_handoffs_card_time", "card_id", "created_time"),
        Index("idx_card_handoffs_target_status", "target_agent_slot_id", "status"),
    )


class HandoffArtifactModel(Base):
    __tablename__ = "handoff_artifacts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    handoff_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("card_handoffs.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    path: Mapped[str] = mapped_column(String(700), nullable=False)
    media_type: Mapped[str] = mapped_column(
        String(255), nullable=False, default="", server_default=""
    )
    created_time: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    handoff: Mapped[CardHandoffModel] = relationship(back_populates="artifacts")

    __table_args__ = (
        UniqueConstraint("handoff_id", "path", name="uq_handoff_artifacts_path"),
        Index("idx_handoff_artifacts_handoff", "handoff_id", "created_time"),
    )
