"""Mark historical CLAUDE.md revisions superseded when they are not active.

Revision ID: 0051_supersede_duplicate_claude_md_revisions
Revises: 0050_user_is_active
Create Date: 2026-08-03
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0051_supersede_duplicate_claude_md_revisions"
down_revision = "0050_user_is_active"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    if not _table_exists("claude_md_revisions") or not _table_exists("projects"):
        return

    # NOT EXISTS is supported by both SQLite and MySQL. A revision is the
    # project's sole active revision only when it is the revision referenced by
    # projects.active_claude_md_revision_id.
    op.execute(
        sa.text(
            "UPDATE claude_md_revisions "
            "SET state = 'superseded' "
            "WHERE state = 'applied' "
            "AND NOT EXISTS ( "
            "SELECT 1 FROM projects "
            "WHERE projects.id = claude_md_revisions.project_id "
            "AND projects.active_claude_md_revision_id = claude_md_revisions.id"
            ")"
        )
    )


def downgrade() -> None:
    # Superseded state is a data repair; the previous applied state cannot be
    # recovered safely because more than one historical row may have existed.
    pass
