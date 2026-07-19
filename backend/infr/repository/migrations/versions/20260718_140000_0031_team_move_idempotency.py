"""Persist wish-card move idempotency keys."""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0031_team_move_idempotency"
down_revision = "0030_team_runtime_links"
branch_labels = None
depends_on = None


def _columns(table: str) -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table)}


def _unique_constraints(table: str) -> set[str]:
    return {
        constraint["name"]
        for constraint in sa.inspect(op.get_bind()).get_unique_constraints(table)
        if constraint.get("name")
    }


def upgrade() -> None:
    if "idempotency_key" not in _columns("card_executions"):
        op.add_column(
            "card_executions",
            sa.Column("idempotency_key", sa.String(255), nullable=True),
        )
    if "uq_card_executions_idempotency" not in _unique_constraints("card_executions"):
        op.create_unique_constraint(
            "uq_card_executions_idempotency",
            "card_executions",
            ["card_id", "idempotency_key"],
        )


def downgrade() -> None:
    if "uq_card_executions_idempotency" in _unique_constraints("card_executions"):
        op.drop_constraint(
            "uq_card_executions_idempotency",
            "card_executions",
            type_="unique",
        )
    if "idempotency_key" in _columns("card_executions"):
        op.drop_column("card_executions", "idempotency_key")
