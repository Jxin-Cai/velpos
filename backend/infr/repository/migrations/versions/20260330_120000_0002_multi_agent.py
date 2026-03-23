"""Add agents_json column, migrate scalar agent fields.

Revision ID: 0002_multi_agent
Revises: 0001_initial
Create Date: 2026-03-30 12:00:00

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0002_multi_agent"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Add JSON column (nullable initially for MySQL 5.x compat)
    op.add_column(
        "projects",
        sa.Column("agents_json", sa.JSON, nullable=True),
    )

    # 2. Set default for rows without data
    op.execute("UPDATE projects SET agents_json = '{}' WHERE agents_json IS NULL")

    # 3. Migrate existing data from scalar columns into agents_json
    op.execute(
        """
        UPDATE projects
        SET agents_json = JSON_OBJECT(
            agent_type,
            JSON_OBJECT('status', agent_init_status, 'session_id', agent_init_session_id)
        )
        WHERE agent_type IS NOT NULL AND agent_type != ''
        """
    )

    # 4. Drop old scalar columns
    op.drop_column("projects", "agent_type")
    op.drop_column("projects", "agent_init_status")
    op.drop_column("projects", "agent_init_session_id")


def downgrade() -> None:
    # Re-add scalar columns
    op.add_column(
        "projects",
        sa.Column("agent_type", sa.String(32), nullable=True),
    )
    op.add_column(
        "projects",
        sa.Column(
            "agent_init_status",
            sa.String(32),
            nullable=False,
            server_default="none",
        ),
    )
    op.add_column(
        "projects",
        sa.Column(
            "agent_init_session_id",
            sa.String(8),
            nullable=False,
            server_default="",
        ),
    )

    # Best-effort: extract first key from agents_json back to scalar columns
    op.execute(
        """
        UPDATE projects
        SET agent_type = JSON_UNQUOTE(JSON_EXTRACT(JSON_KEYS(agents_json), '$[0]')),
            agent_init_status = JSON_UNQUOTE(JSON_EXTRACT(agents_json, CONCAT('$.', JSON_UNQUOTE(JSON_EXTRACT(JSON_KEYS(agents_json), '$[0]')), '.status'))),
            agent_init_session_id = JSON_UNQUOTE(JSON_EXTRACT(agents_json, CONCAT('$.', JSON_UNQUOTE(JSON_EXTRACT(JSON_KEYS(agents_json), '$[0]')), '.session_id')))
        WHERE agents_json != CAST('{}' AS JSON) AND JSON_LENGTH(agents_json) > 0
        """
    )

    op.drop_column("projects", "agents_json")
