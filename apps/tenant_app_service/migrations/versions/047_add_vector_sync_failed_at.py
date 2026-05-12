"""Add last_vector_sync_failed_at for document, asset, and api operation.

Revision ID: 047_add_vector_sync_failed_at
Revises: 046_drop_scheduled_task_runs
Create Date: 2026-05-06
"""

import sqlalchemy as sa
from alembic import op

revision = "047_add_vector_sync_failed_at"
down_revision = "046_drop_scheduled_task_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("last_vector_sync_failed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "asset_metadata",
        sa.Column("last_vector_sync_failed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "api_operation_index",
        sa.Column("last_vector_sync_failed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("api_operation_index", "last_vector_sync_failed_at")
    op.drop_column("asset_metadata", "last_vector_sync_failed_at")
    op.drop_column("documents", "last_vector_sync_failed_at")
