"""Allow large rendered stage outputs on MySQL.

Revision ID: 0043_stage_output_longtext
Revises: 0042_flow_plans_and_leader
Create Date: 2026-07-29 14:00:00
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "0043_stage_output_longtext"
down_revision = "0042_flow_plans_and_leader"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().dialect.name != "mysql":
        return
    op.alter_column(
        "card_stage_outputs",
        "rendered_markdown",
        existing_type=sa.Text(),
        type_=mysql.LONGTEXT(),
        existing_nullable=False,
    )


def downgrade() -> None:
    if op.get_bind().dialect.name != "mysql":
        return
    op.alter_column(
        "card_stage_outputs",
        "rendered_markdown",
        existing_type=mysql.LONGTEXT(),
        type_=sa.Text(),
        existing_nullable=False,
    )
