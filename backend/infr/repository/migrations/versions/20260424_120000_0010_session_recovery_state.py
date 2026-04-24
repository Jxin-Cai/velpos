"""Add session recovery state fields.

Revision ID: 0010_session_recovery_state
Revises: 0009_auth_env_name
Create Date: 2026-04-24 12:00:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision = "0010_session_recovery_state"
down_revision = "0009_auth_env_name"
branch_labels = None
depends_on = None


def _column_exists(table_name: str, column_name: str) -> bool:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    columns = [c["name"] for c in insp.get_columns(table_name)]
    return column_name in columns


def upgrade() -> None:
    if not _column_exists("sessions", "pending_request_context_json"):
        op.add_column(
            "sessions",
            sa.Column(
                "pending_request_context_json",
                mysql.MEDIUMTEXT(),
                nullable=True,
            ),
        )
    if not _column_exists("sessions", "queued_command_json"):
        op.add_column(
            "sessions",
            sa.Column(
                "queued_command_json",
                mysql.TEXT(),
                nullable=True,
            ),
        )
    if not _column_exists("sessions", "cancel_requested"):
        op.add_column(
            "sessions",
            sa.Column(
                "cancel_requested",
                sa.SmallInteger(),
                nullable=False,
                server_default="0",
            ),
        )


def downgrade() -> None:
    if _column_exists("sessions", "cancel_requested"):
        op.drop_column("sessions", "cancel_requested")
    if _column_exists("sessions", "queued_command_json"):
        op.drop_column("sessions", "queued_command_json")
    if _column_exists("sessions", "pending_request_context_json"):
        op.drop_column("sessions", "pending_request_context_json")
