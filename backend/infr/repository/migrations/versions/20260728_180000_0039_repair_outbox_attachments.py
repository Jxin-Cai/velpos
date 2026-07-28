"""Repair missing IM outbox attachment metadata column.

Revision ID: 0039_repair_outbox_attachments
Revises: 0038_im_inbox_attachments
Create Date: 2026-07-28 18:00:00
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0039_repair_outbox_attachments"
down_revision = "0038_im_inbox_attachments"
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
    if _column_exists("im_outbox_messages", "attachments_json"):
        return

    op.add_column(
        "im_outbox_messages",
        sa.Column("attachments_json", sa.Text(), nullable=True),
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
    # 0038 owns this column for fresh databases. This repair migration only
    # reconciles databases that had already applied an earlier form of 0038.
    pass
