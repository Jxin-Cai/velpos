"""Add scheduler IM execution options.

Revision ID: 0022_scheduler_im_options
Revises: 0021_branch_parallel_cols
Create Date: 2026-04-26 10:00:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0022_scheduler_im_options"
down_revision = "0021_branch_parallel_cols"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    return table_name in insp.get_table_names()


def _column_exists(table_name: str, column_name: str) -> bool:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    return column_name in [c["name"] for c in insp.get_columns(table_name)]


def _index_exists(table_name: str, index_name: str) -> bool:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    return index_name in [i["name"] for i in insp.get_indexes(table_name)]


def upgrade() -> None:
    if not _table_exists("scheduled_tasks"):
        return

    for column_name, column_type, server_default in (
        ("channel_id", sa.String(8), ""),
        ("auto_unbind_after_run", sa.SmallInteger(), "1"),
        ("delete_session_on_success", sa.SmallInteger(), "0"),
    ):
        if not _column_exists("scheduled_tasks", column_name):
            op.add_column(
                "scheduled_tasks",
                sa.Column(column_name, column_type, nullable=False, server_default=server_default),
            )

    if not _index_exists("scheduled_tasks", "idx_scheduled_tasks_channel"):
        op.create_index("idx_scheduled_tasks_channel", "scheduled_tasks", ["channel_id"])


def downgrade() -> None:
    if not _table_exists("scheduled_tasks"):
        return

    if _index_exists("scheduled_tasks", "idx_scheduled_tasks_channel"):
        op.drop_index("idx_scheduled_tasks_channel", table_name="scheduled_tasks")

    for column_name in (
        "delete_session_on_success",
        "auto_unbind_after_run",
        "channel_id",
    ):
        if _column_exists("scheduled_tasks", column_name):
            op.drop_column("scheduled_tasks", column_name)
