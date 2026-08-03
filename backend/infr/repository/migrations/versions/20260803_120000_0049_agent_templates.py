"""Create agent_templates table.

Revision ID: 0049_agent_templates
Revises: 0048_scheduler_usage_user_id
Create Date: 2026-08-03
"""
from alembic import op
import sqlalchemy as sa

revision = "0049_agent_templates"
down_revision = "0048_scheduler_usage_user_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_templates",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("name_en", sa.String(128), nullable=False),
        sa.Column("name_zh", sa.String(128), nullable=False),
        sa.Column("description_en", sa.Text(), nullable=False),
        sa.Column("description_zh", sa.Text(), nullable=False),
        sa.Column("category", sa.String(64), nullable=False),
        sa.Column("emoji", sa.String(16), nullable=False, server_default="🤖"),
        sa.Column("color", sa.String(32), nullable=False, server_default="#6366f1"),
        sa.Column("prompt_en", sa.Text(), nullable=False),
        sa.Column("prompt_zh", sa.Text(), nullable=False),
        sa.Column("plugins_config", sa.JSON(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("agent_templates")
