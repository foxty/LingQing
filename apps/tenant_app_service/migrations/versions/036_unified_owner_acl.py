"""Add unified owner_id fields and resource ACL tables.

Revision ID: 036_unified_owner_acl
Revises: 035_api_connector_meta
Create Date: 2026-04-23
"""

import sqlalchemy as sa
from alembic import op

revision = "036_unified_owner_acl"
down_revision = "035_api_connector_meta"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add owner_id to resource tables.
    op.add_column(
        "documents",
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )
    op.add_column(
        "data_sources",
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )
    op.add_column(
        "asset_metadata",
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )
    op.add_column(
        "api_connectors",
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )
    op.add_column(
        "api_operation_index",
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )
    op.add_column(
        "dashboards",
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True),
    )
    op.add_column(
        "reports",
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )
    op.add_column(
        "live_apps",
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )
    op.add_column(
        "scheduled_tasks",
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True),
    )
    op.add_column(
        "artifacts",
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )

    # Create owner-centric indexes used by ACL and list/search filtering.
    op.create_index("idx_documents_tenant_owner", "documents", ["tenant_id", "owner_id"], unique=False)
    op.create_index("idx_data_sources_tenant_owner", "data_sources", ["tenant_id", "owner_id"], unique=False)
    op.create_index("idx_asset_metadata_owner", "asset_metadata", ["owner_id"], unique=False)
    op.create_index("idx_api_connectors_tenant_owner", "api_connectors", ["tenant_id", "owner_id"], unique=False)
    op.create_index(
        "idx_api_operation_tenant_owner",
        "api_operation_index",
        ["tenant_id", "owner_id"],
        unique=False,
    )
    op.create_index("idx_dashboards_owner", "dashboards", ["tenant_id", "owner_id"], unique=False)
    op.create_index("idx_reports_tenant_owner_created", "reports", ["tenant_id", "owner_id", "created_at"], unique=False)
    op.create_index("idx_live_apps_tenant_owner", "live_apps", ["tenant_id", "owner_id"], unique=False)
    op.create_index("idx_scheduled_tasks_tenant_owner", "scheduled_tasks", ["tenant_id", "owner_id"], unique=False)
    op.create_index(
        "idx_artifacts_tenant_owner_type",
        "artifacts",
        ["tenant_id", "owner_id", "artifact_type"],
        unique=False,
    )

    # One-time backfill from legacy owner fields.
    op.execute("UPDATE documents SET owner_id = uploaded_by WHERE owner_id IS NULL")
    op.execute("UPDATE data_sources SET owner_id = created_by WHERE owner_id IS NULL")
    op.execute("UPDATE asset_metadata SET owner_id = created_by WHERE owner_id IS NULL")
    op.execute("UPDATE api_connectors SET owner_id = created_by WHERE owner_id IS NULL")
    op.execute("UPDATE api_operation_index SET owner_id = created_by WHERE owner_id IS NULL")
    op.execute("UPDATE dashboards SET owner_id = created_by WHERE owner_id IS NULL")
    op.execute("UPDATE reports SET owner_id = created_by WHERE owner_id IS NULL")
    op.execute("UPDATE live_apps SET owner_id = created_by WHERE owner_id IS NULL")
    op.execute("UPDATE scheduled_tasks SET owner_id = user_id WHERE owner_id IS NULL")
    op.execute("UPDATE artifacts SET owner_id = created_by WHERE owner_id IS NULL")

    # Unified ACL tables.
    op.create_table(
        "acl_principals",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("principal_type", sa.String(length=20), nullable=False),
        sa.Column("principal_id", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "principal_type", "principal_id", name="uq_acl_principal"),
    )
    op.create_index(
        "idx_acl_principals_tenant_type_id",
        "acl_principals",
        ["tenant_id", "principal_type", "principal_id"],
        unique=False,
    )

    op.create_table(
        "resource_acl",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("resource_type", sa.String(length=50), nullable=False),
        sa.Column("resource_id", sa.Integer(), nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=True),
        sa.Column("inherit_from_type", sa.String(length=50), nullable=True),
        sa.Column("inherit_from_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "resource_type", "resource_id", name="uq_resource_acl_resource"),
    )
    op.create_index("idx_resource_acl_owner", "resource_acl", ["tenant_id", "owner_id"], unique=False)
    op.create_index("idx_resource_acl_resource", "resource_acl", ["tenant_id", "resource_type", "resource_id"], unique=False)

    op.create_table(
        "acl_grants",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("resource_type", sa.String(length=50), nullable=False),
        sa.Column("resource_id", sa.Integer(), nullable=False),
        sa.Column("principal_type", sa.String(length=20), nullable=False),
        sa.Column("principal_id", sa.String(length=128), nullable=False),
        sa.Column("permission", sa.String(length=20), nullable=False),
        sa.Column("effect", sa.String(length=10), nullable=False, server_default="allow"),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "resource_type",
            "resource_id",
            "principal_type",
            "principal_id",
            "permission",
            name="uq_acl_grant",
        ),
    )
    op.create_index("idx_acl_grants_resource", "acl_grants", ["tenant_id", "resource_type", "resource_id"], unique=False)
    op.create_index(
        "idx_acl_grants_principal",
        "acl_grants",
        ["tenant_id", "principal_type", "principal_id", "permission"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_acl_grants_principal", table_name="acl_grants")
    op.drop_index("idx_acl_grants_resource", table_name="acl_grants")
    op.drop_table("acl_grants")

    op.drop_index("idx_resource_acl_resource", table_name="resource_acl")
    op.drop_index("idx_resource_acl_owner", table_name="resource_acl")
    op.drop_table("resource_acl")

    op.drop_index("idx_acl_principals_tenant_type_id", table_name="acl_principals")
    op.drop_table("acl_principals")

    op.drop_index("idx_artifacts_tenant_owner_type", table_name="artifacts")
    op.drop_index("idx_scheduled_tasks_tenant_owner", table_name="scheduled_tasks")
    op.drop_index("idx_live_apps_tenant_owner", table_name="live_apps")
    op.drop_index("idx_reports_tenant_owner_created", table_name="reports")
    op.drop_index("idx_dashboards_owner", table_name="dashboards")
    op.drop_index("idx_api_operation_tenant_owner", table_name="api_operation_index")
    op.drop_index("idx_api_connectors_tenant_owner", table_name="api_connectors")
    op.drop_index("idx_asset_metadata_owner", table_name="asset_metadata")
    op.drop_index("idx_data_sources_tenant_owner", table_name="data_sources")
    op.drop_index("idx_documents_tenant_owner", table_name="documents")

    op.drop_column("artifacts", "owner_id")
    op.drop_column("scheduled_tasks", "owner_id")
    op.drop_column("live_apps", "owner_id")
    op.drop_column("reports", "owner_id")
    op.drop_column("dashboards", "owner_id")
    op.drop_column("api_operation_index", "owner_id")
    op.drop_column("api_connectors", "owner_id")
    op.drop_column("asset_metadata", "owner_id")
    op.drop_column("data_sources", "owner_id")
    op.drop_column("documents", "owner_id")
