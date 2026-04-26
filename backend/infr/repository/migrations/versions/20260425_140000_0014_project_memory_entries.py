"""Add project memory entries.

Revision ID: 0014_project_memory_entries
Revises: 0013_session_run_steps
Create Date: 2026-04-25 14:00:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision = "0014_project_memory_entries"
down_revision = "0013_session_run_steps"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    return table_name in insp.get_table_names()


def upgrade() -> None:
    if not _table_exists("project_memory_entries"):
        op.create_table(
            "project_memory_entries",
            sa.Column("id", sa.String(8), primary_key=True),
            sa.Column("project_id", sa.String(8), nullable=False),
            sa.Column("memory_type", sa.String(32), nullable=False, server_default="note"),
            sa.Column("title", sa.String(255), nullable=False),
            sa.Column("content", mysql.MEDIUMTEXT(), nullable=False),
            sa.Column("source_session_id", sa.String(8), nullable=False, server_default=""),
            sa.Column("source_message_id", sa.String(64), nullable=False, server_default=""),
            sa.Column("visibility", sa.String(32), nullable=False, server_default="project"),
            sa.Column("state", sa.String(16), nullable=False, server_default="active"),
            sa.Column("created_time", sa.DateTime(), nullable=False),
            sa.Column("updated_time", sa.DateTime(), nullable=False),
        )
        op.create_index(
            "idx_project_memory_entries_project_state",
            "project_memory_entries",
            ["project_id", "state", "updated_time"],
        )

    if not _table_exists("session_memory_links"):
        op.create_table(
            "session_memory_links",
            sa.Column("session_id", sa.String(8), nullable=False),
            sa.Column("memory_id", sa.String(8), nullable=False),
            sa.Column("injected_time", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("session_id", "memory_id"),
        )


def downgrade() -> None:
    if _table_exists("session_memory_links"):
        op.drop_table("session_memory_links")
    if _table_exists("project_memory_entries"):
        op.drop_index("idx_project_memory_entries_project_state", table_name="project_memory_entries")
        op.drop_table("project_memory_entries")
