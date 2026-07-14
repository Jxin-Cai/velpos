"""Add scheduler execution and prompt modes.

Revision ID: 0028_scheduler_modes
Revises: 0027_trace_span_session_fk
Create Date: 2026-07-14 21:00:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0028_scheduler_modes"
down_revision = "0027_trace_span_session_fk"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def _column_exists(table_name: str, column_name: str) -> bool:
    return column_name in {
        column["name"] for column in sa.inspect(op.get_bind()).get_columns(table_name)
    }


def upgrade() -> None:
    if not _table_exists("scheduled_tasks"):
        return
    columns = (
        ("execution_mode", sa.String(24), "new_session"),
        ("prompt_mode", sa.String(16), "prompt"),
        ("skill_name", sa.String(255), ""),
    )
    for name, column_type, default in columns:
        if not _column_exists("scheduled_tasks", name):
            op.add_column(
                "scheduled_tasks",
                sa.Column(name, column_type, nullable=False, server_default=default),
            )


def downgrade() -> None:
    if not _table_exists("scheduled_tasks"):
        return
    for name in ("skill_name", "prompt_mode", "execution_mode"):
        if _column_exists("scheduled_tasks", name):
            op.drop_column("scheduled_tasks", name)
