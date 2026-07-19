"""Persist team configuration and execution session links."""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0030_team_runtime_links"
down_revision = "0029_team_persistence"
branch_labels = None
depends_on = None


def _columns(table: str) -> set[str]:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    if "team_config_json" not in _columns("projects"):
        op.add_column("projects", sa.Column("team_config_json", sa.JSON(), nullable=True))
    if "session_id" not in _columns("card_executions"):
        op.add_column("card_executions", sa.Column("session_id", sa.String(8), nullable=True))


def downgrade() -> None:
    if "session_id" in _columns("card_executions"):
        op.drop_column("card_executions", "session_id")
    if "team_config_json" in _columns("projects"):
        op.drop_column("projects", "team_config_json")
