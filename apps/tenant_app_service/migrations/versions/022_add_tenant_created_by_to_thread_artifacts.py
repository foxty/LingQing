"""Add tenant_id and created_by to thread_artifacts for cross-thread artifact gallery.

Revision ID: 022_artifact_gallery
Revises: 021_asset_meta_sync_err
Create Date: 2026-03-17

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "022_artifact_gallery"
down_revision = "021_asset_meta_sync_err"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add tenant_id and created_by columns plus backfill from chat_threads."""
    # Add columns as nullable first so existing rows are accepted
    op.add_column(
        "thread_artifacts",
        sa.Column(
            "tenant_id",
            sa.Integer(),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=True,
            comment="Tenant owning this artifact (for cross-thread listing)",
        ),
    )
    op.add_column(
        "thread_artifacts",
        sa.Column(
            "created_by",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
            comment="User who created this artifact",
        ),
    )

    # Backfill tenant_id from chat_threads for existing rows
    op.execute(
        """
        UPDATE thread_artifacts ta
        SET tenant_id = ct.tenant_id
        FROM chat_threads ct
        WHERE ta.thread_id = ct.id
          AND ta.tenant_id IS NULL
        """
    )

    # Backfill created_by from chat_threads (thread owner) for existing rows
    op.execute(
        """
        UPDATE thread_artifacts ta
        SET created_by = ct.user_id
        FROM chat_threads ct
        WHERE ta.thread_id = ct.id
          AND ta.created_by IS NULL
        """
    )

    # Index for user artifact gallery queries
    op.create_index(
        "idx_thread_artifacts_user_gallery",
        "thread_artifacts",
        ["tenant_id", "created_by", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    """Remove tenant_id and created_by columns."""
    op.drop_index("idx_thread_artifacts_user_gallery", table_name="thread_artifacts")
    op.drop_column("thread_artifacts", "created_by")
    op.drop_column("thread_artifacts", "tenant_id")
