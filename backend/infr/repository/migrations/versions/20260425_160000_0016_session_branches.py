"""Add session branches and snapshots.

Revision ID: 0016_session_branches
Revises: 0015_project_command_policies
Create Date: 2026-04-25 16:00:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision = "0016_session_branches"
down_revision = "0015_project_command_policies"
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
        op.create_table(
            "session_branches",
            sa.Column("id", sa.String(8), primary_key=True),
            sa.Column("source_session_id", sa.String(8), nullable=False),
            sa.Column("branch_session_id", sa.String(8), nullable=False),
            sa.Column("source_message_index", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(255), nullable=False, server_default=""),
            sa.Column("root_session_id", sa.String(8), nullable=False, server_default=""),
            sa.Column("group_id", sa.String(8), nullable=False, server_default=""),
            sa.Column("sequence_no", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("worktree_enabled", sa.Boolean(), nullable=False, server_default="0"),
            sa.Column("worktree_path", sa.String(500), nullable=False, server_default=""),
            sa.Column("base_branch", sa.String(255), nullable=False, server_default=""),
            sa.Column("created_time", sa.DateTime(), nullable=False),
        )
        op.create_index("idx_session_branches_source", "session_branches", ["source_session_id", "created_time"])
        op.create_index("idx_session_branches_branch", "session_branches", ["branch_session_id"])
        op.create_index("idx_session_branches_group", "session_branches", ["group_id", "created_time"])
        op.create_index("idx_session_branches_root", "session_branches", ["root_session_id", "created_time"])
    else:
        for column_name, column_type, server_default in (
            ("root_session_id", sa.String(8), ""),
            ("group_id", sa.String(8), ""),
            ("sequence_no", sa.Integer(), "1"),
            ("worktree_enabled", sa.Boolean(), "0"),
            ("worktree_path", sa.String(500), ""),
            ("base_branch", sa.String(255), ""),
        ):
            if not _column_exists("session_branches", column_name):
                op.add_column("session_branches", sa.Column(column_name, column_type, nullable=False, server_default=server_default))
        if not _index_exists("session_branches", "idx_session_branches_group"):
            op.create_index("idx_session_branches_group", "session_branches", ["group_id", "created_time"])
        if not _index_exists("session_branches", "idx_session_branches_root"):
            op.create_index("idx_session_branches_root", "session_branches", ["root_session_id", "created_time"])

    if not _table_exists("session_snapshots"):
        op.create_table(
            "session_snapshots",
            sa.Column("id", sa.String(8), primary_key=True),
            sa.Column("session_id", sa.String(8), nullable=False),
            sa.Column("message_index", sa.Integer(), nullable=False),
            sa.Column("messages_json", mysql.MEDIUMTEXT(), nullable=False),
            sa.Column("created_time", sa.DateTime(), nullable=False),
        )
        op.create_index("idx_session_snapshots_session", "session_snapshots", ["session_id", "message_index"])


def downgrade() -> None:
    if _table_exists("session_snapshots"):
        op.drop_index("idx_session_snapshots_session", table_name="session_snapshots")
        op.drop_table("session_snapshots")
    if _table_exists("session_branches"):
        op.drop_index("idx_session_branches_branch", table_name="session_branches")
        op.drop_index("idx_session_branches_source", table_name="session_branches")
        op.drop_table("session_branches")
