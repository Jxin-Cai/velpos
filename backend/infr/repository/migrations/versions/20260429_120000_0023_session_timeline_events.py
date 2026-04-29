"""Add session timeline events.

Revision ID: 0023_session_timeline_events
Revises: 0022_scheduler_im_options
Create Date: 2026-04-29 12:00:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision = "0023_session_timeline_events"
down_revision = "0022_scheduler_im_options"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    return table_name in insp.get_table_names()


def upgrade() -> None:
    if _table_exists("session_timeline_events"):
        return
    op.create_table(
        "session_timeline_events",
        sa.Column("id", sa.String(12), primary_key=True),
        sa.Column("session_id", sa.String(8), nullable=False),
        sa.Column("run_id", sa.String(32), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("payload_json", mysql.MEDIUMTEXT(), nullable=False),
        sa.Column("started_time", sa.DateTime(), nullable=False),
        sa.Column("ended_time", sa.DateTime(), nullable=True),
        sa.Column("duration_ms", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("created_time", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("session_id", "run_id", "seq", name="uq_session_timeline_events_run_seq"),
    )
    op.create_index(
        "idx_session_timeline_events_session_time",
        "session_timeline_events",
        ["session_id", "created_time"],
    )
    op.create_index(
        "idx_session_timeline_events_session_run",
        "session_timeline_events",
        ["session_id", "run_id", "seq"],
    )
    op.create_index(
        "idx_session_timeline_events_type",
        "session_timeline_events",
        ["session_id", "event_type", "created_time"],
    )


def downgrade() -> None:
    if _table_exists("session_timeline_events"):
        op.drop_index("idx_session_timeline_events_type", table_name="session_timeline_events")
        op.drop_index("idx_session_timeline_events_session_run", table_name="session_timeline_events")
        op.drop_index("idx_session_timeline_events_session_time", table_name="session_timeline_events")
        op.drop_table("session_timeline_events")
