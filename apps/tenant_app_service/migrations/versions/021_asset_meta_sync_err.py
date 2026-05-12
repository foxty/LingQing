"""Add missing sync error columns to asset_metadata.

Revision ID: 021_asset_meta_sync_err
Revises: 020_doc_vec_sync_err
Create Date: 2026-03-13
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "021_asset_meta_sync_err"
down_revision = "020_doc_vec_sync_err"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add missing sync error fields to asset_metadata table."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = {col["name"] for col in inspector.get_columns("asset_metadata")}

    if "last_metadata_sync_error" not in existing_columns:
        op.add_column(
            "asset_metadata",
            sa.Column(
                "last_metadata_sync_error",
                sa.Text(),
                nullable=True,
                comment="Last metadata sync error message",
            ),
        )

    if "last_vector_sync_error" not in existing_columns:
        op.add_column(
            "asset_metadata",
            sa.Column(
                "last_vector_sync_error",
                sa.Text(),
                nullable=True,
                comment="Last vector sync error message",
            ),
        )


def downgrade() -> None:
    """Remove sync error fields from asset_metadata table."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = {col["name"] for col in inspector.get_columns("asset_metadata")}

    if "last_vector_sync_error" in existing_columns:
        op.drop_column("asset_metadata", "last_vector_sync_error")

    if "last_metadata_sync_error" in existing_columns:
        op.drop_column("asset_metadata", "last_metadata_sync_error")
