"""Add CLAUDE.md revision history.

Revision ID: 0012_claude_md_revisions
Revises: 0011_session_audit_events
Create Date: 2026-04-25 12:00:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision = "0012_claude_md_revisions"
down_revision = "0011_session_audit_events"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    return table_name in insp.get_table_names()


def _column_exists(table_name: str, column_name: str) -> bool:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if table_name not in insp.get_table_names():
        return False
    return column_name in {col["name"] for col in insp.get_columns(table_name)}


def upgrade() -> None:
    if not _column_exists("projects", "active_claude_md_revision_id"):
        op.add_column(
            "projects",
            sa.Column("active_claude_md_revision_id", sa.String(8), nullable=False, server_default=""),
        )
    if not _column_exists("projects", "claude_md_file_hash"):
        op.add_column(
            "projects",
            sa.Column("claude_md_file_hash", sa.String(64), nullable=False, server_default=""),
        )

    if not _table_exists("claude_md_revisions"):
        op.create_table(
            "claude_md_revisions",
            sa.Column("id", sa.String(8), primary_key=True),
            sa.Column("project_id", sa.String(8), nullable=False),
            sa.Column("version_no", sa.Integer(), nullable=False),
            sa.Column("state", sa.String(16), nullable=False),
            sa.Column("content", mysql.MEDIUMTEXT(), nullable=False),
            sa.Column("content_hash", sa.String(64), nullable=False),
            sa.Column("base_revision_id", sa.String(8), nullable=False, server_default=""),
            sa.Column("base_file_hash", sa.String(64), nullable=False, server_default=""),
            sa.Column("created_by", sa.String(32), nullable=False, server_default="user"),
            sa.Column("created_time", sa.DateTime(), nullable=False),
            sa.Column("proposed_time", sa.DateTime(), nullable=True),
            sa.Column("approved_time", sa.DateTime(), nullable=True),
            sa.Column("applied_time", sa.DateTime(), nullable=True),
            sa.Column("rejected_time", sa.DateTime(), nullable=True),
            sa.Column("reject_reason", sa.String(512), nullable=False, server_default=""),
        )
        op.create_index(
            "idx_claude_md_revisions_project_version",
            "claude_md_revisions",
            ["project_id", "version_no"],
        )
        op.create_index(
            "idx_claude_md_revisions_project_state",
            "claude_md_revisions",
            ["project_id", "state"],
        )

    if not _table_exists("claude_md_revision_events"):
        op.create_table(
            "claude_md_revision_events",
            sa.Column("id", sa.String(8), primary_key=True),
            sa.Column("revision_id", sa.String(8), nullable=False),
            sa.Column("from_state", sa.String(16), nullable=False),
            sa.Column("to_state", sa.String(16), nullable=False),
            sa.Column("payload_json", mysql.MEDIUMTEXT(), nullable=False),
            sa.Column("created_time", sa.DateTime(), nullable=False),
        )
        op.create_index(
            "idx_claude_md_revision_events_revision_time",
            "claude_md_revision_events",
            ["revision_id", "created_time"],
        )


def downgrade() -> None:
    if _table_exists("claude_md_revision_events"):
        op.drop_index(
            "idx_claude_md_revision_events_revision_time",
            table_name="claude_md_revision_events",
        )
        op.drop_table("claude_md_revision_events")

    if _table_exists("claude_md_revisions"):
        op.drop_index(
            "idx_claude_md_revisions_project_state",
            table_name="claude_md_revisions",
        )
        op.drop_index(
            "idx_claude_md_revisions_project_version",
            table_name="claude_md_revisions",
        )
        op.drop_table("claude_md_revisions")

    if _column_exists("projects", "claude_md_file_hash"):
        op.drop_column("projects", "claude_md_file_hash")
    if _column_exists("projects", "active_claude_md_revision_id"):
        op.drop_column("projects", "active_claude_md_revision_id")
