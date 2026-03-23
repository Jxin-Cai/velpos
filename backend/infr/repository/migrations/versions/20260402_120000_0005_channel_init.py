"""Create channel_inits table.

Revision ID: 0005_channel_init
Revises: 0004_im_channel_type
Create Date: 2026-04-02 12:00:00

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0005_channel_init"
down_revision = "0004_im_channel_type"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    return table_name in insp.get_table_names()


def upgrade() -> None:
    if _table_exists("channel_inits"):
        return

    op.create_table(
        "channel_inits",
        sa.Column("id", sa.String(8), primary_key=True),
        sa.Column("channel_type", sa.String(32), nullable=False, unique=True),
        sa.Column(
            "init_status",
            sa.String(32),
            nullable=False,
            server_default="not_initialized",
        ),
        sa.Column(
            "config_json",
            sa.String(4096),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "error_message",
            sa.String(1024),
            nullable=False,
            server_default="",
        ),
        sa.Column("created_time", sa.DateTime, nullable=False),
        sa.Column("updated_time", sa.DateTime, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("channel_inits")
