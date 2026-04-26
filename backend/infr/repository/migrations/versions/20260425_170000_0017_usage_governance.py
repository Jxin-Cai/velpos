"""Add usage governance tables.

Revision ID: 0017_usage_governance
Revises: 0016_session_branches
Create Date: 2026-04-25 17:00:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0017_usage_governance"
down_revision = "0016_session_branches"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    return table_name in insp.get_table_names()


def upgrade() -> None:
    if not _table_exists("usage_ledgers"):
        op.create_table(
            "usage_ledgers",
            sa.Column("id", sa.String(8), primary_key=True),
            sa.Column("session_id", sa.String(8), nullable=False),
            sa.Column("project_id", sa.String(8), nullable=False, server_default=""),
            sa.Column("model", sa.String(100), nullable=False, server_default=""),
            sa.Column("input_tokens", sa.BigInteger(), nullable=False, server_default="0"),
            sa.Column("output_tokens", sa.BigInteger(), nullable=False, server_default="0"),
            sa.Column("cache_read_tokens", sa.BigInteger(), nullable=False, server_default="0"),
            sa.Column("cache_creation_tokens", sa.BigInteger(), nullable=False, server_default="0"),
            sa.Column("estimated_cost_usd", sa.Float(), nullable=False, server_default="0"),
            sa.Column("created_time", sa.DateTime(), nullable=False),
        )
        op.create_index("idx_usage_ledgers_session_time", "usage_ledgers", ["session_id", "created_time"])
        op.create_index("idx_usage_ledgers_project_time", "usage_ledgers", ["project_id", "created_time"])

    if not _table_exists("budget_policies"):
        op.create_table(
            "budget_policies",
            sa.Column("id", sa.String(8), primary_key=True),
            sa.Column("project_id", sa.String(8), nullable=False, unique=True),
            sa.Column("daily_token_limit", sa.BigInteger(), nullable=False, server_default="0"),
            sa.Column("daily_cost_limit_usd", sa.Float(), nullable=False, server_default="0"),
            sa.Column("on_exceed", sa.String(16), nullable=False, server_default="warn"),
            sa.Column("updated_time", sa.DateTime(), nullable=False),
        )


def downgrade() -> None:
    if _table_exists("budget_policies"):
        op.drop_table("budget_policies")
    if _table_exists("usage_ledgers"):
        op.drop_index("idx_usage_ledgers_project_time", table_name="usage_ledgers")
        op.drop_index("idx_usage_ledgers_session_time", table_name="usage_ledgers")
        op.drop_table("usage_ledgers")
