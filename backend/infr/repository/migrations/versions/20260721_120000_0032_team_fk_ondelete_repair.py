"""Repair team foreign-key ON DELETE rules on pre-existing databases.

Migration 0029 only creates the team tables when they are absent, so a
database provisioned before the current ondelete rules were finalized can carry
RESTRICT / NO ACTION foreign keys. That makes deleting an archived wish card
with execution/handoff/session history fail at the DB layer. The application
service now cleans dependents explicitly, but this migration realigns the
physical constraints so direct SQL and future code paths behave consistently.

MySQL only. On other dialects (e.g. SQLite used in tests) this is a no-op:
the application-layer ordered cleanup already guarantees correct deletion.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0032_team_fk_ondelete_repair"
down_revision = "0031_team_move_idempotency"
branch_labels = None
depends_on = None


# (table, local_col, referred_table, referred_col, desired_ondelete)
_TARGET_FKS = [
    ("sessions", "card_execution_id", "card_executions", "id", "SET NULL"),
    ("sessions", "agent_slot_id", "team_agent_slots", "id", "SET NULL"),
    ("card_executions", "card_id", "wish_cards", "id", "CASCADE"),
    ("card_handoffs", "card_id", "wish_cards", "id", "CASCADE"),
    ("card_handoffs", "source_execution_id", "card_executions", "id", "CASCADE"),
    ("handoff_artifacts", "handoff_id", "card_handoffs", "id", "CASCADE"),
]


def _table_exists(inspector: sa.engine.reflection.Inspector, table: str) -> bool:
    return table in inspector.get_table_names()


def _find_fk(inspector: sa.engine.reflection.Inspector, table: str, local_col: str):
    for fk in inspector.get_foreign_keys(table):
        if fk.get("constrained_columns") == [local_col]:
            return fk
    return None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "mysql":
        return

    inspector = sa.inspect(bind)
    for table, local_col, ref_table, ref_col, desired in _TARGET_FKS:
        if not _table_exists(inspector, table) or not _table_exists(inspector, ref_table):
            continue

        fk = _find_fk(inspector, table, local_col)
        current = ((fk or {}).get("options") or {}).get("ondelete")
        if fk is not None and (current or "").upper() == desired:
            continue  # already correct

        # Clean orphan references so the rebuilt constraint can be created.
        if desired == "SET NULL":
            op.execute(
                sa.text(
                    f"UPDATE `{table}` SET `{local_col}` = NULL "
                    f"WHERE `{local_col}` IS NOT NULL AND `{local_col}` NOT IN "
                    f"(SELECT `{ref_col}` FROM `{ref_table}`)"
                )
            )
        else:  # CASCADE (or other) — drop rows whose parent is gone
            op.execute(
                sa.text(
                    f"DELETE FROM `{table}` "
                    f"WHERE `{local_col}` IS NOT NULL AND `{local_col}` NOT IN "
                    f"(SELECT `{ref_col}` FROM `{ref_table}`)"
                )
            )

        if fk is not None and fk.get("name"):
            op.drop_constraint(fk["name"], table, type_="foreignkey")
        op.create_foreign_key(
            f"fk_{table}_{local_col}",
            table,
            ref_table,
            [local_col],
            [ref_col],
            ondelete=desired,
        )


def downgrade() -> None:
    # Repair-only migration; the prior ondelete rules are unknown and were, by
    # definition, the source of the delete failures. Nothing to reverse.
    pass
