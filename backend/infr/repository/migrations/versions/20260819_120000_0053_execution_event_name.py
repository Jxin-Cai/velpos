"""Promote the OTel signal name out of the execution event payload.

Per-name tallies previously required deserializing every payload of a run, which
for raw API body events means megabytes per row. A dedicated column lets the
store group by name without touching the payload text.

Revision ID: 0053_execution_event_name
Revises: 0052_execution_events
Create Date: 2026-08-19
"""
from alembic import op
import sqlalchemy as sa

revision = "0053_execution_event_name"
down_revision = "0052_execution_events"
branch_labels = None
depends_on = None

_TABLE_NAME = "execution_events"
_COLUMN_NAME = "event_name"
_INDEX_NAME = "idx_execution_events_run_type_name"
_EVENT_NAME_MAX_LENGTH = 64


def _table_exists(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def _columns(table_name: str) -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table_name)}


def _indexes(table_name: str) -> set[str]:
    return {
        index["name"]
        for index in sa.inspect(op.get_bind()).get_indexes(table_name)
        if index["name"] is not None
    }


def _json_field(column: str, field: str) -> str:
    """Return a dialect-appropriate JSON path read for a text column."""
    if op.get_bind().dialect.name == "mysql":
        return f"JSON_UNQUOTE(JSON_EXTRACT({column}, '$.{field}'))"
    return f"json_extract({column}, '$.{field}')"


def _backfill_event_names() -> None:
    event_name = _json_field("payload_json", "event_name")
    metric_name = _json_field("payload_json", "metric_name")
    op.execute(
        sa.text(
            f"UPDATE {_TABLE_NAME} "
            f"SET {_COLUMN_NAME} = SUBSTR("
            f"  COALESCE({event_name}, {metric_name}, ''), 1, {_EVENT_NAME_MAX_LENGTH}"
            f") "
            f"WHERE event_type IN ('otel_log', 'otel_metric')"
        )
    )


def upgrade() -> None:
    if not _table_exists(_TABLE_NAME):
        return

    if _COLUMN_NAME not in _columns(_TABLE_NAME):
        op.add_column(
            _TABLE_NAME,
            sa.Column(
                _COLUMN_NAME,
                sa.String(_EVENT_NAME_MAX_LENGTH),
                nullable=False,
                server_default="",
            ),
        )
        _backfill_event_names()

    if _INDEX_NAME not in _indexes(_TABLE_NAME):
        op.create_index(
            _INDEX_NAME,
            _TABLE_NAME,
            ["session_id", "run_id", "event_type", _COLUMN_NAME],
        )


def downgrade() -> None:
    if not _table_exists(_TABLE_NAME):
        return

    if _INDEX_NAME in _indexes(_TABLE_NAME):
        op.drop_index(_INDEX_NAME, table_name=_TABLE_NAME)
    if _COLUMN_NAME in _columns(_TABLE_NAME):
        op.drop_column(_TABLE_NAME, _COLUMN_NAME)
