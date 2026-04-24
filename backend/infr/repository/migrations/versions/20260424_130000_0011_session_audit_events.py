"""Add session audit events.

Revision ID: 0011_session_audit_events
Revises: 0010_session_recovery_state
Create Date: 2026-04-24 13:00:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision = "0011_session_audit_events"
down_revision = "0010_session_recovery_state"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    return table_name in insp.get_table_names()


def upgrade() -> None:
    if _table_exists("session_audit_events"):
        return
    op.create_table(
        "session_audit_events",
        sa.Column("id", sa.String(8), primary_key=True),
        sa.Column("session_id", sa.String(8), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("actor", sa.String(32), nullable=False, server_default="system"),
        sa.Column("payload_json", mysql.MEDIUMTEXT(), nullable=True),
        sa.Column("created_time", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "idx_session_audit_events_session_time",
        "session_audit_events",
        ["session_id", "created_time"],
    )


def downgrade() -> None:
    if _table_exists("session_audit_events"):
        op.drop_index(
            "idx_session_audit_events_session_time",
            table_name="session_audit_events",
        )
        op.drop_table("session_audit_events")
