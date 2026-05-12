"""Add ownership fields to data_sources and asset_metadata.

Revision ID: 009_add_ds_asset_ownership
Revises: 008_asset_meta_fields
Create Date: 2026-02-02
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "009_add_ds_asset_ownership"
down_revision = "008_asset_meta_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "data_sources",
        sa.Column(
            "created_by",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "asset_metadata",
        sa.Column(
            "created_by",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("asset_metadata", "created_by")
    op.drop_column("data_sources", "created_by")
