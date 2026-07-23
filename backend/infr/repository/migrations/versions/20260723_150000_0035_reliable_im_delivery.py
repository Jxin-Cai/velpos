"""Add durable, channel-neutral IM inbox and outbox.

Revision ID: 0035_reliable_im_delivery
Revises: 0034_trace_span_ordering
Create Date: 2026-07-23 15:00:00
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0035_reliable_im_delivery"
down_revision = "0034_trace_span_ordering"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    if not _table_exists("im_inbox_events"):
        op.create_table(
            "im_inbox_events",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("channel_id", sa.String(length=36), nullable=False),
            sa.Column("channel_type", sa.String(length=32), nullable=False),
            sa.Column("binding_id", sa.String(length=8), nullable=False),
            sa.Column("session_id", sa.String(length=8), nullable=False),
            sa.Column("external_message_id", sa.String(length=255), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("sender_id", sa.String(length=255), nullable=False, server_default=""),
            sa.Column("group_id", sa.String(length=255), nullable=False, server_default=""),
            sa.Column("status", sa.String(length=16), nullable=False),
            sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("next_attempt_at", sa.DateTime(), nullable=False),
            sa.Column("lease_until", sa.DateTime(), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "channel_id",
                "external_message_id",
                name="uq_im_inbox_channel_message",
            ),
        )
        op.create_index(
            "idx_im_inbox_processable",
            "im_inbox_events",
            ["status", "next_attempt_at", "lease_until"],
        )

    if not _table_exists("im_outbox_messages"):
        op.create_table(
            "im_outbox_messages",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("session_id", sa.String(length=8), nullable=False),
            sa.Column("binding_id", sa.String(length=8), nullable=False),
            sa.Column("channel_id", sa.String(length=36), nullable=False),
            sa.Column("channel_type", sa.String(length=32), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("deduplication_key", sa.String(length=255), nullable=False),
            sa.Column("reply_context_json", sa.Text(), nullable=False),
            sa.Column("status", sa.String(length=16), nullable=False),
            sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("next_attempt_at", sa.DateTime(), nullable=False),
            sa.Column("lease_until", sa.DateTime(), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=False),
            sa.Column("external_message_id", sa.String(length=255), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "deduplication_key",
                name="uq_im_outbox_deduplication_key",
            ),
        )
        op.create_index(
            "idx_im_outbox_processable",
            "im_outbox_messages",
            ["status", "next_attempt_at", "lease_until"],
        )
        op.create_index(
            "idx_im_outbox_session_order",
            "im_outbox_messages",
            ["session_id", "id"],
        )


def downgrade() -> None:
    if _table_exists("im_outbox_messages"):
        op.drop_table("im_outbox_messages")
    if _table_exists("im_inbox_events"):
        op.drop_table("im_inbox_events")
