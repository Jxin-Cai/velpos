"""Add ordering and revision fields to trace spans.

Revision ID: 0034_trace_span_ordering
Revises: 0033_slot_availability
Create Date: 2026-07-21 14:00:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0034_trace_span_ordering"
down_revision = "0033_slot_availability"
branch_labels = None
depends_on = None

_TABLE_NAME = "trace_spans"
_RUN_TOOL_INDEX = "idx_trace_spans_run_tool"


def _table_exists(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def _columns(table_name: str) -> set[str]:
    return {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns(table_name)
    }


def _indexes(table_name: str) -> set[str]:
    return {
        index["name"]
        for index in sa.inspect(op.get_bind()).get_indexes(table_name)
        if index["name"] is not None
    }


def upgrade() -> None:
    if not _table_exists(_TABLE_NAME):
        return

    columns = _columns(_TABLE_NAME)
    if "sequence" not in columns:
        op.add_column(
            _TABLE_NAME,
            sa.Column("sequence", sa.BigInteger(), nullable=False, server_default="0"),
        )
    if "revision" not in columns:
        op.add_column(
            _TABLE_NAME,
            sa.Column("revision", sa.BigInteger(), nullable=False, server_default="1"),
        )

    if _RUN_TOOL_INDEX not in _indexes(_TABLE_NAME):
        op.create_index(
            _RUN_TOOL_INDEX,
            _TABLE_NAME,
            ["session_id", "run_id", "tool_use_id"],
        )


def downgrade() -> None:
    if not _table_exists(_TABLE_NAME):
        return

    if _RUN_TOOL_INDEX in _indexes(_TABLE_NAME):
        op.drop_index(_RUN_TOOL_INDEX, table_name=_TABLE_NAME)

    columns = _columns(_TABLE_NAME)
    if "revision" in columns:
        op.drop_column(_TABLE_NAME, "revision")
    if "sequence" in columns:
        op.drop_column(_TABLE_NAME, "sequence")
