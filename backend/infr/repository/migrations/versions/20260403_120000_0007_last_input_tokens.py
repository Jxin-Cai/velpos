"""Add last_input_tokens to sessions.

Revision ID: 0007_last_input_tokens
Revises: 0006_multi_instance_channels
Create Date: 2026-04-03 12:00:00

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0007_last_input_tokens"
down_revision = "0006_multi_instance_channels"
branch_labels = None
depends_on = None


def _column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    result = bind.execute(sa.text(
        "SELECT COUNT(*) FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :table AND COLUMN_NAME = :column"
    ), {"table": table, "column": column})
    return result.scalar() > 0


def upgrade() -> None:
    if not _column_exists("sessions", "last_input_tokens"):
        op.add_column(
            "sessions",
            sa.Column("last_input_tokens", sa.BigInteger, nullable=False, server_default="0"),
        )


def downgrade() -> None:
    if _column_exists("sessions", "last_input_tokens"):
        op.drop_column("sessions", "last_input_tokens")
