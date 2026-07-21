"""Add availability column to team_agent_slots."""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0033_slot_availability"
down_revision = "0032_team_fk_ondelete_repair"
branch_labels = None
depends_on = None


def _columns(table: str) -> set[str]:
    return {col["name"] for col in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    if "availability" not in _columns("team_agent_slots"):
        op.add_column(
            "team_agent_slots",
            sa.Column("availability", sa.String(16), nullable=False, server_default="available"),
        )


def downgrade() -> None:
    if "availability" in _columns("team_agent_slots"):
        op.drop_column("team_agent_slots", "availability")
