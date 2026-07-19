"""Replace legacy agent teams with team persistence.

Revision ID: 0029_team_persistence
Revises: 0028_scheduler_modes
Create Date: 2026-07-18 12:00:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0029_team_persistence"
down_revision = "0028_scheduler_modes"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def _column_exists(table_name: str, column_name: str) -> bool:
    if not _table_exists(table_name):
        return False
    return column_name in {
        column["name"] for column in sa.inspect(op.get_bind()).get_columns(table_name)
    }


def upgrade() -> None:
    if _table_exists("team_tasks"):
        op.drop_table("team_tasks")

    if _column_exists("projects", "team_config_json"):
        with op.batch_alter_table("projects") as batch_op:
            batch_op.drop_column("team_config_json")

    if _column_exists("sessions", "team_task_id"):
        with op.batch_alter_table("sessions") as batch_op:
            batch_op.drop_column("team_task_id")

    if not _table_exists("teams"):
        op.create_table(
            "teams",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("project_id", sa.String(8), nullable=False),
            sa.Column("name", sa.String(255), nullable=False),
            sa.Column("created_time", sa.DateTime, nullable=False),
            sa.Column("updated_time", sa.DateTime, nullable=False),
            sa.ForeignKeyConstraint(
                ["project_id"], ["projects.id"], name="fk_teams_project", ondelete="CASCADE"
            ),
            sa.UniqueConstraint("project_id", name="uq_teams_project_id"),
        )
        op.create_index("idx_teams_updated", "teams", ["updated_time"])

    if not _table_exists("team_agent_slots"):
        op.create_table(
            "team_agent_slots",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("team_id", sa.String(36), nullable=False),
            sa.Column("name", sa.String(255), nullable=False),
            sa.Column("role", sa.Text, nullable=False),
            sa.Column("workspace_ref", sa.String(512), nullable=False),
            sa.Column("created_time", sa.DateTime, nullable=False),
            sa.ForeignKeyConstraint(
                ["team_id"], ["teams.id"], name="fk_team_agent_slots_team", ondelete="CASCADE"
            ),
            sa.UniqueConstraint("team_id", "name", name="uq_team_agent_slots_name"),
            sa.UniqueConstraint(
                "team_id", "workspace_ref", name="uq_team_agent_slots_workspace"
            ),
        )
        op.create_index(
            "idx_team_agent_slots_team",
            "team_agent_slots",
            ["team_id", "created_time"],
        )

    if not _table_exists("wish_cards"):
        op.create_table(
            "wish_cards",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("team_id", sa.String(36), nullable=False),
            sa.Column("title", sa.String(255), nullable=False),
            sa.Column("description", sa.Text, nullable=False),
            sa.Column("status", sa.String(16), nullable=False),
            sa.Column("assigned_agent_slot_id", sa.String(36), nullable=True),
            sa.Column("created_time", sa.DateTime, nullable=False),
            sa.Column("updated_time", sa.DateTime, nullable=False),
            sa.ForeignKeyConstraint(
                ["team_id"], ["teams.id"], name="fk_wish_cards_team", ondelete="CASCADE"
            ),
            sa.ForeignKeyConstraint(
                ["assigned_agent_slot_id"],
                ["team_agent_slots.id"],
                name="fk_wish_cards_assignee",
                ondelete="SET NULL",
            ),
        )
        op.create_index(
            "idx_wish_cards_team_status",
            "wish_cards",
            ["team_id", "status", "updated_time"],
        )
        op.create_index(
            "idx_wish_cards_assignee", "wish_cards", ["assigned_agent_slot_id"]
        )

    if not _table_exists("card_executions"):
        op.create_table(
            "card_executions",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("card_id", sa.String(36), nullable=False),
            sa.Column("agent_slot_id", sa.String(36), nullable=False),
            sa.Column("status", sa.String(16), nullable=False),
            sa.Column("failure_reason", sa.Text, nullable=True),
            sa.Column("created_time", sa.DateTime, nullable=False),
            sa.Column("started_time", sa.DateTime, nullable=True),
            sa.Column("ended_time", sa.DateTime, nullable=True),
            sa.ForeignKeyConstraint(
                ["card_id"],
                ["wish_cards.id"],
                name="fk_card_executions_card",
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["agent_slot_id"],
                ["team_agent_slots.id"],
                name="fk_card_executions_agent_slot",
                ondelete="RESTRICT",
            ),
        )
        op.create_index(
            "idx_card_executions_card_time",
            "card_executions",
            ["card_id", "created_time"],
        )
        op.create_index(
            "idx_card_executions_slot_status",
            "card_executions",
            ["agent_slot_id", "status"],
        )

    if not _table_exists("card_handoffs"):
        op.create_table(
            "card_handoffs",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("team_id", sa.String(36), nullable=False),
            sa.Column("card_id", sa.String(36), nullable=False),
            sa.Column("source_execution_id", sa.String(36), nullable=False),
            sa.Column("source_agent_slot_id", sa.String(36), nullable=False),
            sa.Column("target_agent_slot_id", sa.String(36), nullable=False),
            sa.Column("summary", sa.Text, nullable=False),
            sa.Column("status", sa.String(16), nullable=False),
            sa.Column("created_time", sa.DateTime, nullable=False),
            sa.Column("resolved_time", sa.DateTime, nullable=True),
            sa.ForeignKeyConstraint(
                ["team_id"], ["teams.id"], name="fk_card_handoffs_team", ondelete="CASCADE"
            ),
            sa.ForeignKeyConstraint(
                ["card_id"],
                ["wish_cards.id"],
                name="fk_card_handoffs_card",
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["source_execution_id"],
                ["card_executions.id"],
                name="fk_card_handoffs_source_execution",
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["source_agent_slot_id"],
                ["team_agent_slots.id"],
                name="fk_card_handoffs_source_slot",
                ondelete="RESTRICT",
            ),
            sa.ForeignKeyConstraint(
                ["target_agent_slot_id"],
                ["team_agent_slots.id"],
                name="fk_card_handoffs_target_slot",
                ondelete="RESTRICT",
            ),
        )
        op.create_index(
            "idx_card_handoffs_card_time", "card_handoffs", ["card_id", "created_time"]
        )
        op.create_index(
            "idx_card_handoffs_target_status",
            "card_handoffs",
            ["target_agent_slot_id", "status"],
        )

    if not _table_exists("handoff_artifacts"):
        op.create_table(
            "handoff_artifacts",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("handoff_id", sa.String(36), nullable=False),
            sa.Column("name", sa.String(255), nullable=False),
            sa.Column("path", sa.String(700), nullable=False),
            sa.Column("media_type", sa.String(255), nullable=False, server_default=""),
            sa.Column("created_time", sa.DateTime, nullable=False),
            sa.ForeignKeyConstraint(
                ["handoff_id"],
                ["card_handoffs.id"],
                name="fk_handoff_artifacts_handoff",
                ondelete="CASCADE",
            ),
            sa.UniqueConstraint("handoff_id", "path", name="uq_handoff_artifacts_path"),
        )
        op.create_index(
            "idx_handoff_artifacts_handoff",
            "handoff_artifacts",
            ["handoff_id", "created_time"],
        )

    if not _column_exists("sessions", "card_execution_id"):
        with op.batch_alter_table("sessions") as batch_op:
            batch_op.add_column(sa.Column("card_execution_id", sa.String(36), nullable=True))
            batch_op.add_column(sa.Column("agent_slot_id", sa.String(36), nullable=True))
            batch_op.create_foreign_key(
                "fk_sessions_card_execution",
                "card_executions",
                ["card_execution_id"],
                ["id"],
                ondelete="SET NULL",
            )
            batch_op.create_foreign_key(
                "fk_sessions_agent_slot",
                "team_agent_slots",
                ["agent_slot_id"],
                ["id"],
                ondelete="SET NULL",
            )
            batch_op.create_index("idx_sessions_card_execution", ["card_execution_id"])
            batch_op.create_index("idx_sessions_agent_slot", ["agent_slot_id"])


def downgrade() -> None:
    with op.batch_alter_table("sessions") as batch_op:
        batch_op.drop_index("idx_sessions_agent_slot")
        batch_op.drop_index("idx_sessions_card_execution")
        batch_op.drop_constraint("fk_sessions_agent_slot", type_="foreignkey")
        batch_op.drop_constraint("fk_sessions_card_execution", type_="foreignkey")
        batch_op.drop_column("agent_slot_id")
        batch_op.drop_column("card_execution_id")

    op.drop_table("handoff_artifacts")
    op.drop_table("card_handoffs")
    op.drop_table("card_executions")
    op.drop_table("wish_cards")
    op.drop_table("team_agent_slots")
    op.drop_table("teams")

    with op.batch_alter_table("projects") as batch_op:
        batch_op.add_column(sa.Column("team_config_json", sa.JSON, nullable=True))

    with op.batch_alter_table("sessions") as batch_op:
        batch_op.add_column(
            sa.Column("team_task_id", sa.String(8), nullable=False, server_default="")
        )

    op.create_table(
        "team_tasks",
        sa.Column("task_id", sa.String(8), primary_key=True),
        sa.Column("main_project_id", sa.String(8), nullable=False),
        sa.Column("coordinator_session_id", sa.String(8), nullable=False),
        sa.Column("target_project_id", sa.String(8), nullable=False),
        sa.Column("target_role", sa.String(64), nullable=False),
        sa.Column("worker_session_id", sa.String(8), nullable=False, server_default=""),
        sa.Column("prompt", sa.Text, nullable=False),
        sa.Column("context_json", sa.JSON, nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("result_summary", sa.Text, nullable=False),
        sa.Column("result_data_json", sa.JSON, nullable=True),
        sa.Column("error_message", sa.Text, nullable=False),
        sa.Column("parent_task_id", sa.String(8), nullable=False, server_default=""),
        sa.Column("depth", sa.Integer, nullable=False, server_default="0"),
        sa.Column("pipeline_step", sa.Integer, nullable=False, server_default="-1"),
        sa.Column("trace_id", sa.String(8), nullable=False, server_default=""),
        sa.Column("created_time", sa.DateTime, nullable=False),
        sa.Column("completed_time", sa.DateTime, nullable=True),
        sa.Column("duration_ms", sa.Integer, nullable=False, server_default="0"),
        sa.Column("cost_usd", sa.Float, nullable=False, server_default="0"),
    )
    op.create_index(
        "ix_team_tasks_main_project_id", "team_tasks", ["main_project_id"]
    )
    op.create_index(
        "ix_team_tasks_coordinator_session_id",
        "team_tasks",
        ["coordinator_session_id"],
    )
