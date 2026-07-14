"""Cascade trace spans when their owning session is deleted.

Revision ID: 0027_trace_span_session_fk
Revises: 0026_trace_spans
Create Date: 2026-07-14 20:00:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0027_trace_span_session_fk"
down_revision = "0026_trace_spans"
branch_labels = None
depends_on = None

_CONSTRAINT_NAME = "fk_trace_spans_session_id_sessions"


def _foreign_key_name() -> str | None:
    inspector = sa.inspect(op.get_bind())
    for fk in inspector.get_foreign_keys("trace_spans"):
        if (
            fk.get("referred_table") == "sessions"
            and fk.get("constrained_columns") == ["session_id"]
        ):
            return fk.get("name")
    return None


def upgrade() -> None:
    if not _foreign_key_name():
        # Older development builds could leave spans behind after deleting a
        # session. Remove those rows before enforcing referential integrity.
        op.execute(sa.text(
            "DELETE trace_spans FROM trace_spans "
            "LEFT JOIN sessions ON sessions.session_id = trace_spans.session_id "
            "WHERE sessions.session_id IS NULL"
        ))
        op.create_foreign_key(
            _CONSTRAINT_NAME,
            "trace_spans",
            "sessions",
            ["session_id"],
            ["session_id"],
            ondelete="CASCADE",
        )


def downgrade() -> None:
    constraint_name = _foreign_key_name()
    if constraint_name:
        op.drop_constraint(constraint_name, "trace_spans", type_="foreignkey")
