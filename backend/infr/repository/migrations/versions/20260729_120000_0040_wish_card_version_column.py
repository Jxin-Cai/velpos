"""Add explicit version column to wish_cards table.

Previously version was derived from len(executions) at runtime.
An explicit column avoids loading the executions relation just to
check version for optimistic locking.
"""

import sqlalchemy as sa
from alembic import op


revision = "0040_wish_card_version_column"
down_revision = "0039_repair_outbox_attachments"


def upgrade() -> None:
    op.add_column(
        "wish_cards",
        sa.Column("version", sa.Integer(), nullable=False, server_default="0"),
    )
    # Backfill existing cards: version = count of executions
    op.execute(
        "UPDATE wish_cards SET version = "
        "(SELECT COUNT(*) FROM card_executions WHERE card_executions.card_id = wish_cards.id)"
    )


def downgrade() -> None:
    op.drop_column("wish_cards", "version")
