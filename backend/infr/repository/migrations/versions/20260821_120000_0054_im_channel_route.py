"""Persist the full channel route on inbound events and widen binding config.

``im_bindings.config_json`` was VARCHAR(2048), which silently truncates once a
channel stores credentials plus routing state. Inbound events only kept
``sender_id``/``group_id``, so channel-private routing fields (such as the
WeChat ``context_token``) were lost whenever a worker reloaded the binding from
the database.

Revision ID: 0054_im_channel_route
Revises: 0053_execution_event_name
Create Date: 2026-08-21 12:00:00
"""
from __future__ import annotations

import json

import sqlalchemy as sa
from alembic import op

revision = "0054_im_channel_route"
down_revision = "0053_execution_event_name"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def _column_exists(table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    if table_name not in inspector.get_table_names():
        return False
    return column_name in {
        column["name"] for column in inspector.get_columns(table_name)
    }


def _backfill_routes() -> None:
    """把历史行的 sender_id / group_id 折叠成 route 结构."""
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            "SELECT id, sender_id, group_id FROM im_inbox_events "
            "WHERE route_json IS NULL"
        )
    ).fetchall()
    for row in rows:
        route = {
            key: value
            for key, value in (("sender_id", row[1]), ("group_id", row[2]))
            if value
        }
        bind.execute(
            sa.text("UPDATE im_inbox_events SET route_json = :route WHERE id = :id"),
            {"route": json.dumps(route, ensure_ascii=False), "id": row[0]},
        )


def upgrade() -> None:
    if _table_exists("im_inbox_events") and not _column_exists(
        "im_inbox_events", "route_json"
    ):
        op.add_column(
            "im_inbox_events",
            sa.Column("route_json", sa.Text(), nullable=True),
        )
        _backfill_routes()
        op.alter_column(
            "im_inbox_events",
            "route_json",
            existing_type=sa.Text(),
            nullable=False,
        )

    if _table_exists("im_bindings"):
        op.alter_column(
            "im_bindings",
            "config_json",
            existing_type=sa.String(length=2048),
            type_=sa.Text(),
            existing_nullable=False,
        )


def downgrade() -> None:
    if _table_exists("im_bindings"):
        op.alter_column(
            "im_bindings",
            "config_json",
            existing_type=sa.Text(),
            type_=sa.String(length=2048),
            existing_nullable=False,
        )
    if _column_exists("im_inbox_events", "route_json"):
        op.drop_column("im_inbox_events", "route_json")
