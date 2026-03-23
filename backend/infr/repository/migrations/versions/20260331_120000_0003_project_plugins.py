"""Add plugins_json column, migrate lark from agents to plugins.

Revision ID: 0003_project_plugins
Revises: 0002_multi_agent
Create Date: 2026-03-31 12:00:00

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0003_project_plugins"
down_revision = "0002_multi_agent"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Add plugins_json column
    op.add_column(
        "projects",
        sa.Column("plugins_json", sa.JSON, nullable=True),
    )

    # 2. Set default for rows without data
    op.execute("UPDATE projects SET plugins_json = '{}' WHERE plugins_json IS NULL")

    # 3. Migrate lark from agents_json to plugins_json
    op.execute(
        """
        UPDATE projects
        SET plugins_json = JSON_OBJECT('lark', JSON_EXTRACT(agents_json, '$.lark')),
            agents_json = JSON_REMOVE(agents_json, '$.lark')
        WHERE JSON_CONTAINS_PATH(agents_json, 'one', '$.lark')
        """
    )


def downgrade() -> None:
    # Move lark back from plugins_json to agents_json
    op.execute(
        """
        UPDATE projects
        SET agents_json = JSON_SET(agents_json, '$.lark', JSON_EXTRACT(plugins_json, '$.lark'))
        WHERE JSON_CONTAINS_PATH(plugins_json, 'one', '$.lark')
        """
    )

    op.drop_column("projects", "plugins_json")
