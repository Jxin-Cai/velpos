"""Add user_id column to channel_inits table.

Revision ID: 0047_channel_init_user_id
Revises: 0046_project_user_id
Create Date: 2026-07-31
"""
from alembic import op
import sqlalchemy as sa

revision = "0047_channel_init_user_id"
down_revision = "0046_project_user_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "channel_inits",
        sa.Column("user_id", sa.Integer(), nullable=False, server_default="1"),
    )
    op.create_index("idx_channel_inits_user_id", "channel_inits", ["user_id"])


def downgrade() -> None:
    op.drop_index("idx_channel_inits_user_id", table_name="channel_inits")
    op.drop_column("channel_inits", "user_id")
