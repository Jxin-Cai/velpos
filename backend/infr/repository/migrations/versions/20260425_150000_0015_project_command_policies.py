"""Add project command policies.

Revision ID: 0015_project_command_policies
Revises: 0014_project_memory_entries
Create Date: 2026-04-25 15:00:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision = "0015_project_command_policies"
down_revision = "0014_project_memory_entries"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    return table_name in insp.get_table_names()


def upgrade() -> None:
    if _table_exists("project_command_policies"):
        return
    op.create_table(
        "project_command_policies",
        sa.Column("id", sa.String(8), primary_key=True),
        sa.Column("project_id", sa.String(8), nullable=False),
        sa.Column("command_name", sa.String(128), nullable=False),
        sa.Column("command_type", sa.String(32), nullable=False, server_default="unknown"),
        sa.Column("enabled", sa.SmallInteger(), nullable=False, server_default="1"),
        sa.Column("visible", sa.SmallInteger(), nullable=False, server_default="1"),
        sa.Column("default_args_json", mysql.JSON(), nullable=True),
        sa.Column("updated_time", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("project_id", "command_name", "command_type", name="uq_project_command_policy"),
    )
    op.create_index(
        "idx_project_command_policies_project",
        "project_command_policies",
        ["project_id"],
    )


def downgrade() -> None:
    if _table_exists("project_command_policies"):
        op.drop_index("idx_project_command_policies_project", table_name="project_command_policies")
        op.drop_table("project_command_policies")
