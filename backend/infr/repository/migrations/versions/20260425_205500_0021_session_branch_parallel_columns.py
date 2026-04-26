"""Add parallel session branch columns.

Revision ID: 0021_branch_parallel_cols
Revises: 0020_evolution_proposals
Create Date: 2026-04-25 20:55:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0021_branch_parallel_cols"
down_revision = "0020_evolution_proposals"
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
    if not _table_exists("session_branches"):
        return

    for column_name, column_type, server_default in (
        ("root_session_id", sa.String(8), ""),
        ("group_id", sa.String(8), ""),
        ("sequence_no", sa.Integer(), "1"),
        ("worktree_enabled", sa.Boolean(), "0"),
        ("worktree_path", sa.String(500), ""),
        ("base_branch", sa.String(255), ""),
    ):
        if not _column_exists("session_branches", column_name):
            op.add_column(
                "session_branches",
                sa.Column(column_name, column_type, nullable=False, server_default=server_default),
            )

    if not _index_exists("session_branches", "idx_session_branches_group"):
        op.create_index("idx_session_branches_group", "session_branches", ["group_id", "created_time"])
    if not _index_exists("session_branches", "idx_session_branches_root"):
        op.create_index("idx_session_branches_root", "session_branches", ["root_session_id", "created_time"])


def downgrade() -> None:
    if not _table_exists("session_branches"):
        return

    if _index_exists("session_branches", "idx_session_branches_root"):
        op.drop_index("idx_session_branches_root", table_name="session_branches")
    if _index_exists("session_branches", "idx_session_branches_group"):
        op.drop_index("idx_session_branches_group", table_name="session_branches")

    for column_name in (
        "base_branch",
        "worktree_path",
        "worktree_enabled",
        "sequence_no",
        "group_id",
        "root_session_id",
    ):
        if _column_exists("session_branches", column_name):
            op.drop_column("session_branches", column_name)
