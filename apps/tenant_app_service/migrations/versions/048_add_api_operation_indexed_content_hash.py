"""Add content/indexed hash fields for vector sync state.

Revision ID: 048_op_doc_asset_hash_sync
Revises: 047_add_vector_sync_failed_at
Create Date: 2026-05-06
"""

import sqlalchemy as sa
from alembic import op

revision = "048_op_doc_asset_hash_sync"
down_revision = "047_add_vector_sync_failed_at"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("content_hash", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "documents",
        sa.Column("indexed_content_hash", sa.String(length=128), nullable=True),
    )

    op.add_column(
        "asset_metadata",
        sa.Column("content_hash", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "asset_metadata",
        sa.Column("indexed_content_hash", sa.String(length=128), nullable=True),
    )

    op.add_column(
        "api_operation_index",
        sa.Column("indexed_content_hash", sa.String(length=128), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("api_operation_index", "indexed_content_hash")
    op.drop_column("asset_metadata", "indexed_content_hash")
    op.drop_column("asset_metadata", "content_hash")
    op.drop_column("documents", "indexed_content_hash")
    op.drop_column("documents", "content_hash")
