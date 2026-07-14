"""Add trace_spans table for session monitoring.

Revision ID: 0026_trace_spans
Revises: 0025_trace_id
Create Date: 2026-07-10 12:00:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision = "0026_trace_spans"
down_revision = "0025_trace_id"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    return table_name in insp.get_table_names()


def upgrade() -> None:
    if _table_exists("trace_spans"):
        return
    op.create_table(
        "trace_spans",
        sa.Column("id", sa.String(16), primary_key=True),
        sa.Column("session_id", sa.String(8), nullable=False),
        sa.Column("run_id", sa.String(32), nullable=False),
        sa.Column("parent_span_id", sa.String(16), nullable=True),
        sa.Column("span_type", sa.String(32), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("agent_id", sa.String(64), nullable=True),
        sa.Column("tool_use_id", sa.String(64), nullable=True),
        sa.Column("input_preview", mysql.MEDIUMTEXT(), nullable=True),
        sa.Column("output_preview", mysql.MEDIUMTEXT(), nullable=True),
        sa.Column("metadata_json", mysql.MEDIUMTEXT(), nullable=False),
        sa.Column("started_time", sa.DateTime(), nullable=False),
        sa.Column("ended_time", sa.DateTime(), nullable=True),
        sa.Column("duration_ms", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("created_time", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "idx_trace_spans_session_run",
        "trace_spans",
        ["session_id", "run_id", "started_time"],
    )
    op.create_index(
        "idx_trace_spans_tool_use",
        "trace_spans",
        ["session_id", "tool_use_id"],
    )
    op.create_index(
        "idx_trace_spans_agent",
        "trace_spans",
        ["session_id", "agent_id"],
    )
    op.create_index(
        "idx_trace_spans_parent",
        "trace_spans",
        ["parent_span_id"],
    )


def downgrade() -> None:
    if _table_exists("trace_spans"):
        op.drop_index("idx_trace_spans_parent", table_name="trace_spans")
        op.drop_index("idx_trace_spans_agent", table_name="trace_spans")
        op.drop_index("idx_trace_spans_tool_use", table_name="trace_spans")
        op.drop_index("idx_trace_spans_session_run", table_name="trace_spans")
        op.drop_table("trace_spans")
