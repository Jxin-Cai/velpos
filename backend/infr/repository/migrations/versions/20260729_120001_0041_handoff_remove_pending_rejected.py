"""Migrate any leftover PENDING handoffs to ACCEPTED.

The domain model no longer supports PENDING or REJECTED states.
In practice no PENDING rows exist (they were always accepted immediately
before being persisted), but this migration ensures safety.
"""

from alembic import op


revision = "0041_handoff_cleanup"
down_revision = "0040_wish_card_version_column"


def upgrade() -> None:
    op.execute("UPDATE card_handoffs SET status = 'accepted' WHERE status = 'pending'")
    op.execute("UPDATE card_handoffs SET status = 'accepted' WHERE status = 'rejected'")


def downgrade() -> None:
    pass
