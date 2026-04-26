"""Add file attachments.

Revision ID: 0019_attachments
Revises: 0018_scheduled_tasks
Create Date: 2026-04-25 19:00:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0019_attachments"
down_revision = "0018_scheduled_tasks"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    return table_name in insp.get_table_names()


def upgrade() -> None:
    if not _table_exists("attachments"):
        op.create_table(
            "attachments",
            sa.Column("id", sa.String(8), primary_key=True),
            sa.Column("project_id", sa.String(8), nullable=False, server_default=""),
            sa.Column("session_id", sa.String(8), nullable=False, server_default=""),
            sa.Column("filename", sa.String(255), nullable=False),
            sa.Column("mime_type", sa.String(128), nullable=False),
            sa.Column("size_bytes", sa.BigInteger(), nullable=False, server_default="0"),
            sa.Column("storage_path", sa.String(1024), nullable=False),
            sa.Column("sha256", sa.String(64), nullable=False),
            sa.Column("created_time", sa.DateTime(), nullable=False),
        )
        op.create_index("idx_attachments_session", "attachments", ["session_id", "created_time"])
        op.create_index("idx_attachments_project", "attachments", ["project_id"])
    if not _table_exists("message_attachments"):
        op.create_table(
            "message_attachments",
            sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column("message_id", sa.String(32), nullable=False),
            sa.Column("attachment_id", sa.String(8), nullable=False),
            sa.UniqueConstraint("message_id", "attachment_id", name="uq_message_attachment"),
        )
        op.create_index("idx_message_attachments_message", "message_attachments", ["message_id"])
        op.create_index("idx_message_attachments_attachment", "message_attachments", ["attachment_id"])


def downgrade() -> None:
    if _table_exists("message_attachments"):
        op.drop_index("idx_message_attachments_attachment", table_name="message_attachments")
        op.drop_index("idx_message_attachments_message", table_name="message_attachments")
        op.drop_table("message_attachments")
    if _table_exists("attachments"):
        op.drop_index("idx_attachments_project", table_name="attachments")
        op.drop_index("idx_attachments_session", table_name="attachments")
        op.drop_table("attachments")
