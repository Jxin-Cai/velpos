"""Add auth_env_name column to channel_profiles.

Revision ID: 0009_auth_env_name
Revises: 0008_ensure_channel_profiles
Create Date: 2026-04-07 18:00:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0009_auth_env_name"
down_revision = "0008_ensure_channel_profiles"
branch_labels = None
depends_on = None


def _column_exists(table_name: str, column_name: str) -> bool:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    columns = [c["name"] for c in insp.get_columns(table_name)]
    return column_name in columns


def upgrade() -> None:
    if _column_exists("channel_profiles", "auth_env_name"):
        return
    op.add_column(
        "channel_profiles",
        sa.Column(
            "auth_env_name",
            sa.String(64),
            nullable=False,
            server_default="ANTHROPIC_API_KEY",
        ),
    )


def downgrade() -> None:
    op.drop_column("channel_profiles", "auth_env_name")
