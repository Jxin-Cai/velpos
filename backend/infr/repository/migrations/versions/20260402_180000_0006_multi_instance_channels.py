"""Multi-instance channels: add name to channel_inits, add channel_id to im_bindings.

Revision ID: 0006_multi_instance_channels
Revises: 0005_channel_init
Create Date: 2026-04-02 18:00:00

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0006_multi_instance_channels"
down_revision = "0005_channel_init"
branch_labels = None
depends_on = None


def _column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    result = bind.execute(sa.text(
        "SELECT COUNT(*) FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :table AND COLUMN_NAME = :column"
    ), {"table": table, "column": column})
    return result.scalar() > 0


def _constraint_exists(table: str, constraint: str) -> bool:
    bind = op.get_bind()
    result = bind.execute(sa.text(
        "SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :table AND CONSTRAINT_NAME = :constraint"
    ), {"table": table, "constraint": constraint})
    return result.scalar() > 0


def _index_exists(table: str, index: str) -> bool:
    bind = op.get_bind()
    result = bind.execute(sa.text(
        "SELECT COUNT(*) FROM information_schema.STATISTICS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :table AND INDEX_NAME = :index"
    ), {"table": table, "index": index})
    return result.scalar() > 0


def upgrade() -> None:
    # ── channel_inits: add name, drop unique on channel_type ──
    if not _column_exists("channel_inits", "name"):
        op.add_column(
            "channel_inits",
            sa.Column("name", sa.String(128), nullable=False, server_default=""),
        )
        # Backfill: set name = channel_type for existing rows
        op.execute(sa.text("UPDATE channel_inits SET name = channel_type WHERE name = ''"))

    # Drop unique constraint on channel_type (allow multiple instances per type)
    if _constraint_exists("channel_inits", "channel_type"):
        op.drop_constraint("channel_type", "channel_inits", type_="unique")

    # Add index for lookups by channel_type
    if not _index_exists("channel_inits", "ix_channel_inits_type"):
        op.create_index("ix_channel_inits_type", "channel_inits", ["channel_type"])

    # ── im_bindings: add channel_id, change constraints ──
    if not _column_exists("im_bindings", "channel_id"):
        op.add_column(
            "im_bindings",
            sa.Column("channel_id", sa.String(8), nullable=False, server_default=""),
        )
        # Backfill: match channel_id from channel_inits by channel_type
        op.execute(sa.text(
            "UPDATE im_bindings b "
            "JOIN channel_inits ci ON ci.channel_type = b.channel_type "
            "SET b.channel_id = ci.id "
            "WHERE b.channel_id = ''"
        ))

    # Drop old unique constraint (session_id, channel_type)
    if _constraint_exists("im_bindings", "uq_im_bindings_session_channel"):
        op.drop_constraint("uq_im_bindings_session_channel", "im_bindings", type_="unique")

    # New: one channel instance can only bind to one session
    if not _constraint_exists("im_bindings", "uq_im_bindings_channel_id"):
        op.create_unique_constraint(
            "uq_im_bindings_channel_id",
            "im_bindings",
            ["channel_id"],
        )

    # New: one session can only have one binding
    if not _constraint_exists("im_bindings", "uq_im_bindings_session"):
        op.create_unique_constraint(
            "uq_im_bindings_session",
            "im_bindings",
            ["session_id"],
        )


def downgrade() -> None:
    # Restore im_bindings constraints
    if _constraint_exists("im_bindings", "uq_im_bindings_session"):
        op.drop_constraint("uq_im_bindings_session", "im_bindings", type_="unique")
    if _constraint_exists("im_bindings", "uq_im_bindings_channel_id"):
        op.drop_constraint("uq_im_bindings_channel_id", "im_bindings", type_="unique")
    if not _constraint_exists("im_bindings", "uq_im_bindings_session_channel"):
        op.create_unique_constraint(
            "uq_im_bindings_session_channel",
            "im_bindings",
            ["session_id", "channel_type"],
        )
    if _column_exists("im_bindings", "channel_id"):
        op.drop_column("im_bindings", "channel_id")

    # Restore channel_inits
    if _index_exists("channel_inits", "ix_channel_inits_type"):
        op.drop_index("ix_channel_inits_type", "channel_inits")
    if not _constraint_exists("channel_inits", "channel_type"):
        op.create_unique_constraint("channel_type", "channel_inits", ["channel_type"])
    if _column_exists("channel_inits", "name"):
        op.drop_column("channel_inits", "name")
