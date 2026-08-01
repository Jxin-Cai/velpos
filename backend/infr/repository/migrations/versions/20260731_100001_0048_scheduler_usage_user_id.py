"""Add user_id to scheduled_tasks and usage_ledgers.

Revision ID: 0048_scheduler_usage_user_id
Revises: 0047_channel_init_user_id
Create Date: 2026-07-31
"""
from alembic import op
import sqlalchemy as sa

revision = "0048_scheduler_usage_user_id"
down_revision = "0047_channel_init_user_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "scheduled_tasks",
        sa.Column("user_id", sa.Integer(), nullable=False, server_default="1"),
    )
    op.create_index("idx_scheduled_tasks_user_id", "scheduled_tasks", ["user_id"])

    op.add_column(
        "usage_ledgers",
        sa.Column("user_id", sa.Integer(), nullable=False, server_default="1"),
    )
    op.create_index("idx_usage_ledgers_user_time", "usage_ledgers", ["user_id", "created_time"])


def downgrade() -> None:
    op.drop_index("idx_usage_ledgers_user_time", table_name="usage_ledgers")
    op.drop_column("usage_ledgers", "user_id")
    op.drop_index("idx_scheduled_tasks_user_id", table_name="scheduled_tasks")
    op.drop_column("scheduled_tasks", "user_id")
