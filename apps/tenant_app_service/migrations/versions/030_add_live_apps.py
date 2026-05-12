"""Add live_apps table.

Revision ID: 030_add_live_apps
Revises: 029_add_user_preferences
Create Date: 2026-03-31
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "030_add_live_apps"
down_revision = "029_add_user_preferences"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "live_apps",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("data_source_id", sa.Integer(), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("entry_file", sa.String(length=255), nullable=False, server_default="entry.html"),
        sa.Column("app_config", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("sdk_version", sa.String(length=20), nullable=False, server_default="1.0"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="draft"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["data_source_id"], ["data_sources.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "name", name="uq_live_apps_tenant_name"),
    )

    op.create_index("idx_live_apps_tenant_status", "live_apps", ["tenant_id", "status"], unique=False)
    op.create_index("idx_live_apps_data_source", "live_apps", ["data_source_id"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_live_apps_data_source", table_name="live_apps")
    op.drop_index("idx_live_apps_tenant_status", table_name="live_apps")
    op.drop_table("live_apps")
