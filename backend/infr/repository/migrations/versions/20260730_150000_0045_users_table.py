"""Create users table and seed default admin.

Revision ID: 0045_users_table
Revises: 0044_execution_evidence
Create Date: 2026-07-30
"""
from alembic import op
import sqlalchemy as sa

revision = "0045_users_table"
down_revision = "0044_execution_evidence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("username", sa.String(64), nullable=False),
        sa.Column("display_name", sa.String(128), nullable=False),
        sa.Column("role", sa.String(16), nullable=False, server_default="member"),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("created_time", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("username", name="uq_users_username"),
    )

    op.execute(
        "INSERT INTO users (id, username, display_name, role, hashed_password, created_time) "
        "VALUES (1, 'admin', 'Admin', 'admin', '', '2024-01-01 00:00:00')"
    )


def downgrade() -> None:
    op.drop_table("users")
