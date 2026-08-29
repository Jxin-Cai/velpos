"""Add source and source_ref columns to market entry tables.

Revision ID: 0056_market_entry_source
Revises: 0055_market_entries
Create Date: 2026-08-29
"""
from alembic import op
import sqlalchemy as sa

revision = "0056_market_entry_source"
down_revision = "0055_market_entries"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("mcp_server_entries", "skill_entries"):
        op.add_column(
            table,
            sa.Column("source", sa.String(16), nullable=False, server_default="custom"),
        )
        op.add_column(
            table,
            sa.Column("source_ref", sa.String(256), nullable=False, server_default=""),
        )
        op.create_index(f"ix_{table}_source", table, ["source"])


def downgrade() -> None:
    for table in ("skill_entries", "mcp_server_entries"):
        op.drop_index(f"ix_{table}_source", table_name=table)
        op.drop_column(table, "source_ref")
        op.drop_column(table, "source")
