"""Drop legacy ownership columns superseded by owner_id.

Revision ID: 041_drop_legacy_owner_cols
Revises: 040_drop_artifact_shares
Create Date: 2026-04-26
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "041_drop_legacy_owner_cols"
down_revision = "040_drop_artifact_shares"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("idx_documents_uploaded_by", table_name="documents")
    op.drop_column("documents", "uploaded_by")

    op.drop_column("asset_metadata", "created_by")

    op.drop_index("idx_artifacts_user_gallery", table_name="artifacts")
    op.create_index("idx_artifacts_user_gallery", "artifacts", ["tenant_id", "owner_id", "created_at"])
    op.drop_column("artifacts", "created_by")

    op.drop_index("idx_reports_user_created", table_name="reports")
    op.drop_index("idx_reports_created_by", table_name="reports")
    op.drop_column("reports", "created_by")

    op.drop_index("idx_dashboards_created_by", table_name="dashboards")
    op.drop_column("dashboards", "created_by")

    op.drop_column("live_apps", "created_by")


def downgrade() -> None:
    op.add_column("live_apps", sa.Column("created_by", sa.Integer(), nullable=True))
    op.create_foreign_key(None, "live_apps", "users", ["created_by"], ["id"], ondelete="SET NULL")
    op.execute("UPDATE live_apps SET created_by = owner_id WHERE created_by IS NULL AND owner_id IS NOT NULL")

    op.add_column("dashboards", sa.Column("created_by", sa.Integer(), nullable=True))
    op.create_foreign_key(None, "dashboards", "users", ["created_by"], ["id"], ondelete="CASCADE")
    op.execute("UPDATE dashboards SET created_by = owner_id WHERE created_by IS NULL AND owner_id IS NOT NULL")
    op.create_index("idx_dashboards_created_by", "dashboards", ["created_by"])

    op.add_column("reports", sa.Column("created_by", sa.Integer(), nullable=True))
    op.create_foreign_key(None, "reports", "users", ["created_by"], ["id"], ondelete="SET NULL")
    op.execute("UPDATE reports SET created_by = owner_id WHERE created_by IS NULL AND owner_id IS NOT NULL")
    op.create_index("idx_reports_created_by", "reports", ["created_by"])
    op.create_index("idx_reports_user_created", "reports", ["tenant_id", "created_by", "created_at"])

    op.add_column("artifacts", sa.Column("created_by", sa.Integer(), nullable=True))
    op.create_foreign_key(None, "artifacts", "users", ["created_by"], ["id"], ondelete="SET NULL")
    op.execute("UPDATE artifacts SET created_by = owner_id WHERE created_by IS NULL AND owner_id IS NOT NULL")
    op.drop_index("idx_artifacts_user_gallery", table_name="artifacts")
    op.create_index("idx_artifacts_user_gallery", "artifacts", ["tenant_id", "created_by", "created_at"])

    op.add_column("asset_metadata", sa.Column("created_by", sa.Integer(), nullable=True))
    op.create_foreign_key(None, "asset_metadata", "users", ["created_by"], ["id"], ondelete="SET NULL")
    op.execute("UPDATE asset_metadata SET created_by = owner_id WHERE created_by IS NULL AND owner_id IS NOT NULL")

    op.add_column("documents", sa.Column("uploaded_by", sa.Integer(), nullable=True))
    op.create_foreign_key(None, "documents", "users", ["uploaded_by"], ["id"], ondelete="SET NULL")
    op.execute("UPDATE documents SET uploaded_by = owner_id WHERE uploaded_by IS NULL AND owner_id IS NOT NULL")
    op.create_index("idx_documents_uploaded_by", "documents", ["uploaded_by"])
