"""Ensure channel_profiles table exists.

Revision ID: 0008_ensure_channel_profiles
Revises: 0007_last_input_tokens
Create Date: 2026-04-07 12:00:00

Baseline may stamp 0001_initial without creating channel_profiles
if the DB was bootstrapped before that table was added.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0008_ensure_channel_profiles"
down_revision = "0007_last_input_tokens"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    return table_name in insp.get_table_names()


def upgrade() -> None:
    if _table_exists("channel_profiles"):
        return

    op.create_table(
        "channel_profiles",
        sa.Column("profile_id", sa.String(8), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("host", sa.String(512), nullable=False, server_default=""),
        sa.Column("api_key", sa.String(512), nullable=False, server_default=""),
        sa.Column("model_config", sa.Text, nullable=False),
        sa.Column("is_active", sa.SmallInteger, nullable=False, server_default="0"),
        sa.Column("created_time", sa.DateTime, nullable=False),
        sa.Column("updated_time", sa.DateTime, nullable=False),
        sa.Index("idx_channel_profiles_is_active", "is_active"),
    )


def downgrade() -> None:
    op.drop_table("channel_profiles")
