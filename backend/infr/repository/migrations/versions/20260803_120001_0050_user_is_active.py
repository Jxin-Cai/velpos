"""Add is_active column to users table.

Revision ID: 0050_user_is_active
Revises: 0049_agent_templates
Create Date: 2026-08-03
"""
from alembic import op
import sqlalchemy as sa

revision = "0050_user_is_active"
down_revision = "0049_agent_templates"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
    )


def downgrade() -> None:
    op.drop_column("users", "is_active")
