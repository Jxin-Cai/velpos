"""Add flow plans, flow plan steps, and leader/attribution columns.

Revision ID: 0042_flow_plans_and_leader
Revises: 0041_handoff_cleanup
Create Date: 2026-07-29 13:00:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0042_flow_plans_and_leader"
down_revision = "0041_handoff_cleanup"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def _columns(table: str) -> set[str]:
    return {col["name"] for col in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    # --- Add columns to existing tables ---

    if "slot_role" not in _columns("team_agent_slots"):
        op.add_column(
            "team_agent_slots",
            sa.Column("slot_role", sa.String(20), nullable=False, server_default="worker"),
        )
    slots = sa.table(
        "team_agent_slots",
        sa.column("id", sa.String),
        sa.column("team_id", sa.String),
        sa.column("slot_role", sa.String),
        sa.column("created_time", sa.DateTime),
    )
    bind = op.get_bind()
    team_ids = bind.execute(sa.select(slots.c.team_id).distinct()).scalars().all()
    for team_id in team_ids:
        has_leader = bind.execute(
            sa.select(slots.c.id)
            .where(
                slots.c.team_id == team_id,
                slots.c.slot_role == "leader",
            )
            .limit(1)
        ).scalar_one_or_none()
        if has_leader is not None:
            continue
        first_slot_id = bind.execute(
            sa.select(slots.c.id)
            .where(slots.c.team_id == team_id)
            .order_by(slots.c.created_time.asc(), slots.c.id.asc())
            .limit(1)
        ).scalar_one_or_none()
        if first_slot_id is not None:
            bind.execute(
                slots.update()
                .where(slots.c.id == first_slot_id)
                .values(slot_role="leader")
            )

    if "leader_session_id" not in _columns("teams"):
        op.add_column(
            "teams",
            sa.Column("leader_session_id", sa.String(64), nullable=True),
        )

    if "failure_category" not in _columns("card_executions"):
        op.add_column(
            "card_executions",
            sa.Column("failure_category", sa.String(40), nullable=True),
        )
    if "triggered_by" not in _columns("card_executions"):
        op.add_column(
            "card_executions",
            sa.Column("triggered_by", sa.String(128), nullable=True),
        )
    if "timeout_at" not in _columns("card_executions"):
        op.add_column(
            "card_executions",
            sa.Column("timeout_at", sa.DateTime, nullable=True),
        )

    if "creator_id" not in _columns("wish_cards"):
        op.add_column(
            "wish_cards",
            sa.Column("creator_id", sa.String(128), nullable=True),
        )
    if "attribution_chain" not in _columns("wish_cards"):
        op.add_column(
            "wish_cards",
            sa.Column("attribution_chain", sa.Text, nullable=True),
        )

    # --- Create new tables ---

    if not _table_exists("flow_plans"):
        op.create_table(
            "flow_plans",
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column("team_id", sa.String(64), nullable=False),
            sa.Column("card_id", sa.String(64), nullable=False),
            sa.Column("leader_slot_id", sa.String(64), nullable=False),
            sa.Column("mode", sa.String(20), nullable=False),
            sa.Column("status", sa.String(20), nullable=False),
            sa.Column("leader_session_id", sa.String(64), nullable=True),
            sa.Column("created_at", sa.DateTime, nullable=False),
            sa.Column("updated_at", sa.DateTime, nullable=False),
            sa.ForeignKeyConstraint(
                ["team_id"], ["teams.id"], name="fk_flow_plans_team", ondelete="CASCADE"
            ),
            sa.ForeignKeyConstraint(
                ["card_id"], ["wish_cards.id"], name="fk_flow_plans_card", ondelete="CASCADE"
            ),
        )
        op.create_index("idx_flow_plans_card_status", "flow_plans", ["card_id", "status"])

    if not _table_exists("flow_plan_steps"):
        op.create_table(
            "flow_plan_steps",
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column("flow_plan_id", sa.String(64), nullable=False),
            sa.Column("sequence", sa.Integer, nullable=False),
            sa.Column("target_slot_id", sa.String(64), nullable=False),
            sa.Column("status", sa.String(20), nullable=False),
            sa.Column("execution_id", sa.String(64), nullable=True),
            sa.Column("started_at", sa.DateTime, nullable=True),
            sa.Column("ended_at", sa.DateTime, nullable=True),
            sa.ForeignKeyConstraint(
                ["flow_plan_id"],
                ["flow_plans.id"],
                name="fk_flow_plan_steps_plan",
                ondelete="CASCADE",
            ),
        )
        op.create_index(
            "idx_flow_plan_steps_execution", "flow_plan_steps", ["execution_id"]
        )


def downgrade() -> None:
    if _table_exists("flow_plan_steps"):
        op.drop_table("flow_plan_steps")
    if _table_exists("flow_plans"):
        op.drop_table("flow_plans")

    if "attribution_chain" in _columns("wish_cards"):
        op.drop_column("wish_cards", "attribution_chain")
    if "creator_id" in _columns("wish_cards"):
        op.drop_column("wish_cards", "creator_id")

    if "timeout_at" in _columns("card_executions"):
        op.drop_column("card_executions", "timeout_at")
    if "triggered_by" in _columns("card_executions"):
        op.drop_column("card_executions", "triggered_by")
    if "failure_category" in _columns("card_executions"):
        op.drop_column("card_executions", "failure_category")

    if "leader_session_id" in _columns("teams"):
        op.drop_column("teams", "leader_session_id")

    if "slot_role" in _columns("team_agent_slots"):
        op.drop_column("team_agent_slots", "slot_role")
