"""Initial schema - all tables.

Revision ID: 0001_initial
Revises:
Create Date: 2026-03-29 12:00:00

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.mysql import MEDIUMTEXT

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- projects ---
    op.create_table(
        "projects",
        sa.Column("id", sa.String(8), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("dir_path", sa.String(512), nullable=False),
        sa.Column("agent_type", sa.String(32), nullable=True),
        sa.Column("agent_init_status", sa.String(32), nullable=False, server_default="none"),
        sa.Column("agent_init_session_id", sa.String(8), nullable=False, server_default=""),
        sa.Column("sort_order", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_time", sa.DateTime, nullable=False),
        sa.Column("updated_time", sa.DateTime, nullable=True),
    )

    # --- sessions ---
    op.create_table(
        "sessions",
        sa.Column("session_id", sa.String(8), primary_key=True),
        sa.Column("project_id", sa.String(8), nullable=False, server_default=""),
        sa.Column("model", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("messages", MEDIUMTEXT, nullable=False),
        sa.Column("input_tokens", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("continue_conversation", sa.SmallInteger, nullable=False, server_default="0"),
        sa.Column("project_dir", sa.String(512), nullable=False, server_default=""),
        sa.Column("name", sa.String(255), nullable=False, server_default=""),
        sa.Column("sdk_session_id", sa.String(64), nullable=False, server_default=""),
        sa.Column("created_time", sa.DateTime, nullable=False),
        sa.Column("updated_time", sa.DateTime, nullable=False),
    )

    # --- im_bindings ---
    op.create_table(
        "im_bindings",
        sa.Column("id", sa.String(8), primary_key=True),
        sa.Column("session_id", sa.String(8), nullable=False),
        sa.Column("im_user_id", sa.String(64), nullable=False),
        sa.Column("im_token", sa.String(512), nullable=False, server_default=""),
        sa.Column("binding_status", sa.String(16), nullable=False),
        sa.Column("friend_user_id", sa.String(64), nullable=False, server_default=""),
        sa.Column("qr_code_data", sa.String(512), nullable=False, server_default=""),
        sa.Column("created_time", sa.DateTime, nullable=False),
        sa.Column("updated_time", sa.DateTime, nullable=False),
        sa.UniqueConstraint("session_id", name="uq_im_bindings_session_id"),
    )

    # --- channel_profiles ---
    op.create_table(
        "channel_profiles",
        sa.Column("profile_id", sa.String(8), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("host", sa.String(512), nullable=False, server_default=""),
        sa.Column("api_key", sa.String(512), nullable=False, server_default=""),
        sa.Column("model_config", sa.Text, nullable=False),
        sa.Column("is_active", sa.SmallInteger, nullable=False, server_default="0"),
        sa.Column("created_time", sa.DateTime, nullable=False),
        sa.Column("updated_time", sa.DateTime, nullable=False),
        sa.Index("idx_channel_profiles_is_active", "is_active"),
    )


def downgrade() -> None:
    op.drop_table("channel_profiles")
    op.drop_table("im_bindings")
    op.drop_table("sessions")
    op.drop_table("projects")
