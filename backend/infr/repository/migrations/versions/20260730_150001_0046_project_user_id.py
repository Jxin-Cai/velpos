"""Add user_id column to projects table.

Revision ID: 0046_project_user_id
Revises: 0045_users_table
Create Date: 2026-07-30
"""
from alembic import op
import sqlalchemy as sa

revision = "0046_project_user_id"
down_revision = "0045_users_table"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column("user_id", sa.Integer(), nullable=False, server_default="1"),
    )
    op.create_index("idx_projects_user_id", "projects", ["user_id"])


def downgrade() -> None:
    op.drop_index("idx_projects_user_id", table_name="projects")
    op.drop_column("projects", "user_id")
