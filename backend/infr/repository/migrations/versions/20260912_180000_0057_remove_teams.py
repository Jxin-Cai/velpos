"""Remove teams, boards, and leftover team columns.

Revision ID: 0057_remove_teams
Revises: 0056_market_entry_source
Create Date: 2026-09-12
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0057_remove_teams"
down_revision = "0056_market_entry_source"
branch_labels = None
depends_on = None

_TEAM_TABLES = (
    "stage_output_artifacts",
    "handoff_artifacts",
    "flow_plan_steps",
    "flow_plans",
    "card_handoffs",
    "card_stage_outputs",
    "card_executions",
    "wish_cards",
    "team_agent_slots",
    "teams",
    "team_tasks",
)


def _table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def _columns(table_name: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if table_name not in inspector.get_table_names():
        return set()
    return {column["name"] for column in inspector.get_columns(table_name)}


def _indexes(table_name: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if table_name not in inspector.get_table_names():
        return set()
    return {index["name"] for index in inspector.get_indexes(table_name) if index.get("name")}


_SESSION_TEAM_COLUMNS = ("card_execution_id", "agent_slot_id", "team_task_id")
_SESSION_TEAM_TABLES = {"card_executions", "team_agent_slots", "team_tasks"}


def upgrade() -> None:
    if _table_exists("sessions"):
        bind = op.get_bind()
        inspector = sa.inspect(bind)
        session_columns = _columns("sessions")
        session_indexes = _indexes("sessions")
        session_fks = inspector.get_foreign_keys("sessions")
        with op.batch_alter_table("sessions") as batch_op:
            for fk in session_fks:
                referred = fk.get("referred_table")
                constrained = set(fk.get("constrained_columns") or [])
                if referred in _SESSION_TEAM_TABLES or constrained.intersection(_SESSION_TEAM_COLUMNS):
                    if fk.get("name"):
                        batch_op.drop_constraint(fk["name"], type_="foreignkey")
            if "idx_sessions_card_execution" in session_indexes:
                batch_op.drop_index("idx_sessions_card_execution")
            if "idx_sessions_agent_slot" in session_indexes:
                batch_op.drop_index("idx_sessions_agent_slot")
            for column_name in _SESSION_TEAM_COLUMNS:
                if column_name in session_columns:
                    batch_op.drop_column(column_name)

    bind = op.get_bind()
    if bind.dialect.name == "mysql":
        op.execute(sa.text("SET FOREIGN_KEY_CHECKS=0"))
    try:
        for table_name in _TEAM_TABLES:
            if _table_exists(table_name):
                op.drop_table(table_name)
        if _table_exists("projects") and "project_type" in _columns("projects"):
            if _table_exists("sessions"):
                op.execute(sa.text(
                    "DELETE FROM sessions WHERE project_id IN "
                    "(SELECT id FROM projects WHERE project_type = 'team')"
                ))
            op.execute(sa.text("DELETE FROM projects WHERE project_type = 'team'"))
    finally:
        if bind.dialect.name == "mysql":
            op.execute(sa.text("SET FOREIGN_KEY_CHECKS=1"))

    if _table_exists("projects") and "team_config_json" in _columns("projects"):
        with op.batch_alter_table("projects") as batch_op:
            batch_op.drop_column("team_config_json")


def downgrade() -> None:
    raise NotImplementedError("Teams removal is not reversible")
