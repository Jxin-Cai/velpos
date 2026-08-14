"""Add append-only execution event ledger.

Revision ID: 0052_execution_events
Revises: 0051_supersede_duplicate_claude_md_revisions
Create Date: 2026-08-13
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.mysql import MEDIUMTEXT

revision = "0052_execution_events"
down_revision = "0051_supersede_duplicate_claude_md_revisions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "execution_events",
        sa.Column("position", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("event_id", sa.String(32), nullable=False),
        sa.Column("session_id", sa.String(8), nullable=False),
        sa.Column("run_id", sa.String(32), nullable=False),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("span_id", sa.String(16), nullable=False),
        sa.Column("parent_span_id", sa.String(16), nullable=True),
        sa.Column("span_type", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("agent_id", sa.String(64), nullable=True),
        sa.Column("tool_use_id", sa.String(64), nullable=True),
        sa.Column("causation_event_id", sa.String(32), nullable=True),
        sa.Column("event_time", sa.DateTime(), nullable=False),
        sa.Column("ingested_time", sa.DateTime(), nullable=False),
        sa.Column("payload_json", MEDIUMTEXT(), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.session_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("position"),
        sa.UniqueConstraint("event_id", name="uq_execution_events_event_id"),
    )
    op.create_index(
        "idx_execution_events_session_run_position",
        "execution_events",
        ["session_id", "run_id", "position"],
    )
    op.create_index(
        "idx_execution_events_span_position",
        "execution_events",
        ["span_id", "position"],
    )


def downgrade() -> None:
    op.drop_index("idx_execution_events_span_position", table_name="execution_events")
    op.drop_index("idx_execution_events_session_run_position", table_name="execution_events")
    op.drop_table("execution_events")
