"""Create mcp_server_entries and skill_entries market tables.

Revision ID: 0055_market_entries
Revises: 0054_im_channel_route
Create Date: 2026-08-29
"""
from alembic import op
import sqlalchemy as sa

revision = "0055_market_entries"
down_revision = "0054_im_channel_route"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mcp_server_entries",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("display_name", sa.String(128), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("category", sa.String(64), nullable=False),
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.Column("transport", sa.String(16), nullable=False, server_default="stdio"),
        sa.Column("server_config", sa.JSON(), nullable=True),
        sa.Column("repo_url", sa.String(512), nullable=False, server_default=""),
        sa.Column("homepage_url", sa.String(512), nullable=False, server_default=""),
        sa.Column("author", sa.String(128), nullable=False, server_default=""),
        sa.Column("version", sa.String(64), nullable=False, server_default=""),
        sa.Column("logo_emoji", sa.String(16), nullable=False, server_default="🔌"),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_mcp_server_entries_name"),
    )
    op.create_index("ix_mcp_server_entries_category", "mcp_server_entries", ["category"])

    op.create_table(
        "skill_entries",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("display_name", sa.String(128), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("category", sa.String(64), nullable=False),
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("repo_url", sa.String(512), nullable=False, server_default=""),
        sa.Column("author", sa.String(128), nullable=False, server_default=""),
        sa.Column("version", sa.String(64), nullable=False, server_default=""),
        sa.Column("logo_emoji", sa.String(16), nullable=False, server_default="🎯"),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_skill_entries_name"),
    )
    op.create_index("ix_skill_entries_category", "skill_entries", ["category"])


def downgrade() -> None:
    op.drop_index("ix_skill_entries_category", table_name="skill_entries")
    op.drop_table("skill_entries")
    op.drop_index("ix_mcp_server_entries_category", table_name="mcp_server_entries")
    op.drop_table("mcp_server_entries")
