"""Add vector sync status fields to api_operation_index.

Revision ID: 038_api_op_vector_sync_status
Revises: 037_backfill_artifact_owner_id
Create Date: 2026-04-24
"""

import sqlalchemy as sa
from alembic import op

revision = "038_api_op_vector_sync_status"
down_revision = "037_backfill_artifact_owner_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "api_operation_index",
        sa.Column("last_vector_synced_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "api_operation_index",
        sa.Column("last_vector_sync_error", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("api_operation_index", "last_vector_sync_error")
    op.drop_column("api_operation_index", "last_vector_synced_at")
