"""Add channel_type, channel_address, config_json to im_bindings.

Revision ID: 0004_im_channel_type
Revises: 0003_project_plugins
Create Date: 2026-04-01 12:00:00

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0004_im_channel_type"
down_revision = "0003_project_plugins"
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


def upgrade() -> None:
    if not _column_exists("im_bindings", "channel_type"):
        op.add_column(
            "im_bindings",
            sa.Column("channel_type", sa.String(32), nullable=False, server_default="openim"),
        )
    if not _column_exists("im_bindings", "channel_address"):
        op.add_column(
            "im_bindings",
            sa.Column("channel_address", sa.String(256), nullable=False, server_default=""),
        )
    if not _column_exists("im_bindings", "config_json"):
        op.add_column(
            "im_bindings",
            sa.Column("config_json", sa.String(2048), nullable=False, server_default="{}"),
        )

    # Drop old unique constraint on session_id alone (if exists)
    if _constraint_exists("im_bindings", "uq_im_bindings_session_id"):
        op.drop_constraint("uq_im_bindings_session_id", "im_bindings", type_="unique")

    # New unique constraint: one binding per (session_id, channel_type)
    if not _constraint_exists("im_bindings", "uq_im_bindings_session_channel"):
        op.create_unique_constraint(
            "uq_im_bindings_session_channel",
            "im_bindings",
            ["session_id", "channel_type"],
        )


def downgrade() -> None:
    if _constraint_exists("im_bindings", "uq_im_bindings_session_channel"):
        op.drop_constraint("uq_im_bindings_session_channel", "im_bindings", type_="unique")
    if not _constraint_exists("im_bindings", "uq_im_bindings_session_id"):
        op.create_unique_constraint(
            "uq_im_bindings_session_id", "im_bindings", ["session_id"]
        )
    if _column_exists("im_bindings", "config_json"):
        op.drop_column("im_bindings", "config_json")
    if _column_exists("im_bindings", "channel_address"):
        op.drop_column("im_bindings", "channel_address")
    if _column_exists("im_bindings", "channel_type"):
        op.drop_column("im_bindings", "channel_type")
