"""Backfill artifacts.owner_id from created_by when missing.

Revision ID: 037_backfill_artifact_owner_id
Revises: 036_unified_owner_acl
Create Date: 2026-04-23
"""

from alembic import op

revision = "037_backfill_artifact_owner_id"
down_revision = "036_unified_owner_acl"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("UPDATE artifacts SET owner_id = created_by WHERE owner_id IS NULL AND created_by IS NOT NULL")


def downgrade() -> None:
    # Irreversible data backfill migration.
    pass
