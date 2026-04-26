"""Add scheduled tasks.

Revision ID: 0018_scheduled_tasks
Revises: 0017_usage_governance
Create Date: 2026-04-25 18:00:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision = "0018_scheduled_tasks"
down_revision = "0017_usage_governance"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    return table_name in insp.get_table_names()


def upgrade() -> None:
    if not _table_exists("scheduled_tasks"):
        op.create_table(
            "scheduled_tasks",
            sa.Column("id", sa.String(8), primary_key=True),
            sa.Column("project_id", sa.String(8), nullable=False, server_default=""),
            sa.Column("session_id", sa.String(8), nullable=False, server_default=""),
            sa.Column("name", sa.String(255), nullable=False),
            sa.Column("prompt", mysql.MEDIUMTEXT(), nullable=False),
            sa.Column("cron_expr", sa.String(64), nullable=False),
            sa.Column("enabled", sa.SmallInteger(), nullable=False, server_default="1"),
            sa.Column("next_run_time", sa.DateTime(), nullable=True),
            sa.Column("created_time", sa.DateTime(), nullable=False),
        )
        op.create_index("idx_scheduled_tasks_next", "scheduled_tasks", ["enabled", "next_run_time"])
        op.create_index("idx_scheduled_tasks_project", "scheduled_tasks", ["project_id"])
    if not _table_exists("scheduled_task_runs"):
        op.create_table(
            "scheduled_task_runs",
            sa.Column("id", sa.String(8), primary_key=True),
            sa.Column("task_id", sa.String(8), nullable=False),
            sa.Column("status", sa.String(16), nullable=False),
            sa.Column("started_time", sa.DateTime(), nullable=False),
            sa.Column("ended_time", sa.DateTime(), nullable=True),
            sa.Column("result_session_id", sa.String(8), nullable=False, server_default=""),
            sa.Column("error_message", sa.String(500), nullable=False, server_default=""),
        )
        op.create_index("idx_scheduled_task_runs_task_time", "scheduled_task_runs", ["task_id", "started_time"])


def downgrade() -> None:
    if _table_exists("scheduled_task_runs"):
        op.drop_index("idx_scheduled_task_runs_task_time", table_name="scheduled_task_runs")
        op.drop_table("scheduled_task_runs")
    if _table_exists("scheduled_tasks"):
        op.drop_index("idx_scheduled_tasks_project", table_name="scheduled_tasks")
        op.drop_index("idx_scheduled_tasks_next", table_name="scheduled_tasks")
        op.drop_table("scheduled_tasks")
