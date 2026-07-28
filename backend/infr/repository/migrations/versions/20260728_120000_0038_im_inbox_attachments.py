"""Persist IM inbox and outbox attachment metadata.

Revision ID: 0038_im_inbox_attachments
Revises: 0037_team_agent_projects
Create Date: 2026-07-28 12:00:00
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0038_im_inbox_attachments"
down_revision = "0037_team_agent_projects"
branch_labels = None
depends_on = None


def _column_exists(table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    if table_name not in inspector.get_table_names():
        return False
    return column_name in {
        column["name"] for column in inspector.get_columns(table_name)
    }


def upgrade() -> None:
    if not _column_exists("im_inbox_events", "attachments_json"):
        op.add_column(
            "im_inbox_events",
            sa.Column(
                "attachments_json",
                sa.Text(),
                nullable=True,
            ),
        )
        op.execute(
            sa.text(
                "UPDATE im_inbox_events "
                "SET attachments_json = '[]' "
                "WHERE attachments_json IS NULL"
            )
        )
        op.alter_column(
            "im_inbox_events",
            "attachments_json",
            existing_type=sa.Text(),
            nullable=False,
        )
    if not _column_exists("im_outbox_messages", "attachments_json"):
        op.add_column(
            "im_outbox_messages",
            sa.Column(
                "attachments_json",
                sa.Text(),
                nullable=True,
            ),
        )
        op.execute(
            sa.text(
                "UPDATE im_outbox_messages "
                "SET attachments_json = '[]' "
                "WHERE attachments_json IS NULL"
            )
        )
        op.alter_column(
            "im_outbox_messages",
            "attachments_json",
            existing_type=sa.Text(),
            nullable=False,
        )


def downgrade() -> None:
    if _column_exists("im_outbox_messages", "attachments_json"):
        op.drop_column("im_outbox_messages", "attachments_json")
    if _column_exists("im_inbox_events", "attachments_json"):
        op.drop_column("im_inbox_events", "attachments_json")
