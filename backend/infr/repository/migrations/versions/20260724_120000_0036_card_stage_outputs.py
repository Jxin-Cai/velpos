"""Persist versioned wish-card stage outputs.

Revision ID: 0036_card_stage_outputs
Revises: 0035_reliable_im_delivery
Create Date: 2026-07-24 12:00:00
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0036_card_stage_outputs"
down_revision = "0035_reliable_im_delivery"
branch_labels = None
depends_on = None
def upgrade() -> None:
    op.create_table(
        "card_stage_outputs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("card_id", sa.String(36), nullable=False),
        sa.Column("execution_id", sa.String(36), nullable=False),
        sa.Column("previous_output_id", sa.String(36), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("content_json", sa.JSON(), nullable=False),
        sa.Column("rendered_markdown", sa.Text(), nullable=False),
        sa.Column("source_session_id", sa.String(8), nullable=False),
        sa.Column("checksum", sa.String(64), nullable=False),
        sa.Column("compression_method", sa.String(64), nullable=False),
        sa.Column("created_time", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["card_id"], ["wish_cards.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["execution_id"], ["card_executions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["previous_output_id"], ["card_stage_outputs.id"], ondelete="SET NULL"
        ),
        sa.UniqueConstraint(
            "execution_id",
            "revision",
            name="uq_card_stage_outputs_execution_revision",
        ),
    )
    op.create_index(
        "idx_card_stage_outputs_card_time",
        "card_stage_outputs",
        ["card_id", "created_time"],
    )
    op.create_index(
        "idx_card_stage_outputs_execution_revision",
        "card_stage_outputs",
        ["execution_id", "revision"],
    )

    op.create_table(
        "stage_output_artifacts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("stage_output_id", sa.String(36), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("path", sa.String(700), nullable=False),
        sa.Column("media_type", sa.String(255), nullable=False, server_default=""),
        sa.Column("created_time", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["stage_output_id"], ["card_stage_outputs.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint(
            "stage_output_id", "path", name="uq_stage_output_artifacts_path"
        ),
    )
    op.create_index(
        "idx_stage_output_artifacts_output",
        "stage_output_artifacts",
        ["stage_output_id", "created_time"],
    )

    with op.batch_alter_table("card_executions") as batch_op:
        batch_op.add_column(
            sa.Column("input_stage_output_id", sa.String(36), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_card_executions_input_stage_output",
            "card_stage_outputs",
            ["input_stage_output_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index(
            "idx_card_executions_input_output", ["input_stage_output_id"]
        )

    with op.batch_alter_table("card_handoffs") as batch_op:
        batch_op.add_column(
            sa.Column("target_execution_id", sa.String(36), nullable=True)
        )
        batch_op.add_column(sa.Column("stage_output_id", sa.String(36), nullable=True))
        batch_op.add_column(sa.Column("consumed_revision", sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column("consumed_checksum", sa.String(64), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_card_handoffs_target_execution",
            "card_executions",
            ["target_execution_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_foreign_key(
            "fk_card_handoffs_stage_output",
            "card_stage_outputs",
            ["stage_output_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index(
            "idx_card_handoffs_target_execution", ["target_execution_id"]
        )
        batch_op.create_index("idx_card_handoffs_stage_output", ["stage_output_id"])


def downgrade() -> None:
    with op.batch_alter_table("card_handoffs") as batch_op:
        batch_op.drop_index("idx_card_handoffs_stage_output")
        batch_op.drop_index("idx_card_handoffs_target_execution")
        batch_op.drop_constraint("fk_card_handoffs_stage_output", type_="foreignkey")
        batch_op.drop_constraint(
            "fk_card_handoffs_target_execution", type_="foreignkey"
        )
        batch_op.drop_column("consumed_checksum")
        batch_op.drop_column("consumed_revision")
        batch_op.drop_column("stage_output_id")
        batch_op.drop_column("target_execution_id")

    with op.batch_alter_table("card_executions") as batch_op:
        batch_op.drop_index("idx_card_executions_input_output")
        batch_op.drop_constraint(
            "fk_card_executions_input_stage_output", type_="foreignkey"
        )
        batch_op.drop_column("input_stage_output_id")

    op.drop_table("stage_output_artifacts")
    op.drop_table("card_stage_outputs")
