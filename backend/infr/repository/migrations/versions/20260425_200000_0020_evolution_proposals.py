"""Add evolution proposals.

Revision ID: 0020_evolution_proposals
Revises: 0019_attachments
Create Date: 2026-04-25 20:00:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision = "0020_evolution_proposals"
down_revision = "0019_attachments"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    return table_name in insp.get_table_names()


def upgrade() -> None:
    if not _table_exists("evolution_proposals"):
        op.create_table(
            "evolution_proposals",
            sa.Column("id", sa.String(8), primary_key=True),
            sa.Column("project_id", sa.String(8), nullable=False, server_default=""),
            sa.Column("source_session_id", sa.String(8), nullable=False, server_default=""),
            sa.Column("state", sa.String(16), nullable=False),
            sa.Column("extracted_lessons_json", mysql.MEDIUMTEXT(), nullable=False),
            sa.Column("proposed_claude_md_revision_id", sa.String(8), nullable=False, server_default=""),
            sa.Column("created_time", sa.DateTime(), nullable=False),
            sa.Column("updated_time", sa.DateTime(), nullable=False),
        )
        op.create_index("idx_evolution_proposals_project", "evolution_proposals", ["project_id", "updated_time"])
        op.create_index("idx_evolution_proposals_session", "evolution_proposals", ["source_session_id"])


def downgrade() -> None:
    if _table_exists("evolution_proposals"):
        op.drop_index("idx_evolution_proposals_session", table_name="evolution_proposals")
        op.drop_index("idx_evolution_proposals_project", table_name="evolution_proposals")
        op.drop_table("evolution_proposals")
