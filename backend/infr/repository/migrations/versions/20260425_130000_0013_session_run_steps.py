"""Add session run steps.

Revision ID: 0013_session_run_steps
Revises: 0012_claude_md_revisions
Create Date: 2026-04-25 13:00:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision = "0013_session_run_steps"
down_revision = "0012_claude_md_revisions"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    return table_name in insp.get_table_names()


def upgrade() -> None:
    if _table_exists("session_run_steps"):
        return
    op.create_table(
        "session_run_steps",
        sa.Column("id", sa.String(8), primary_key=True),
        sa.Column("session_id", sa.String(8), nullable=False),
        sa.Column("run_id", sa.String(8), nullable=False),
        sa.Column("step_type", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("payload_json", mysql.MEDIUMTEXT(), nullable=False),
        sa.Column("started_time", sa.DateTime(), nullable=False),
        sa.Column("ended_time", sa.DateTime(), nullable=True),
        sa.Column("duration_ms", sa.BigInteger(), nullable=False, server_default="0"),
    )
    op.create_index(
        "idx_session_run_steps_session_run",
        "session_run_steps",
        ["session_id", "run_id", "started_time"],
    )
    op.create_index(
        "idx_session_run_steps_session_time",
        "session_run_steps",
        ["session_id", "started_time"],
    )


def downgrade() -> None:
    if _table_exists("session_run_steps"):
        op.drop_index("idx_session_run_steps_session_time", table_name="session_run_steps")
        op.drop_index("idx_session_run_steps_session_run", table_name="session_run_steps")
        op.drop_table("session_run_steps")
