"""Add structured execution attribution and failure evidence.

Revision ID: 0044_execution_evidence
Revises: 0043_stage_output_longtext
Create Date: 2026-07-30 12:00:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0044_execution_evidence"
down_revision = "0043_stage_output_longtext"
branch_labels = None
depends_on = None


def _columns() -> set[str]:
    return {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns("card_executions")
    }


def upgrade() -> None:
    columns = _columns()
    additions = (
        ("failure_phase", sa.String(40)),
        ("failure_retryable", sa.Boolean()),
        ("delegated_by_slot_id", sa.String(36)),
        ("flow_plan_id", sa.String(64)),
        ("flow_step_id", sa.String(64)),
    )
    for name, column_type in additions:
        if name not in columns:
            op.add_column(
                "card_executions",
                sa.Column(name, column_type, nullable=True),
            )
    flow_step_columns = {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns("flow_plan_steps")
    }
    if "leader_notified_at" not in flow_step_columns:
        op.add_column(
            "flow_plan_steps",
            sa.Column("leader_notified_at", sa.DateTime(), nullable=True),
        )


def downgrade() -> None:
    flow_step_columns = {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns("flow_plan_steps")
    }
    if "leader_notified_at" in flow_step_columns:
        op.drop_column("flow_plan_steps", "leader_notified_at")
    columns = _columns()
    for name in (
        "flow_step_id",
        "flow_plan_id",
        "delegated_by_slot_id",
        "failure_retryable",
        "failure_phase",
    ):
        if name in columns:
            op.drop_column("card_executions", name)
