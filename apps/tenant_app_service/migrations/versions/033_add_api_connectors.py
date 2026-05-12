"""Add api connectors and operation index tables.

Revision ID: 033_add_api_connectors
Revises: 032_remove_report_public_share
Create Date: 2026-04-20
"""

import sqlalchemy as sa
from alembic import op

revision = "033_add_api_connectors"
down_revision = "032_remove_report_public_share"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "api_connectors",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("base_url", sa.String(length=1024), nullable=False),
        sa.Column("auth_type", sa.String(length=50), nullable=False, server_default="none"),
        sa.Column("auth_config", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("rate_policy", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("schema_source_type", sa.String(length=50), nullable=False),
        sa.Column("schema_source_url", sa.String(length=2048), nullable=True),
        sa.Column("schema_last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "name", name="uq_api_connectors_tenant_name"),
    )
    op.create_index("idx_api_connectors_tenant_status", "api_connectors", ["tenant_id", "status"], unique=False)

    op.create_table(
        "api_operation_index",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("connector_id", sa.Integer(), nullable=False),
        sa.Column("operation_uid", sa.String(length=64), nullable=False),
        sa.Column("method", sa.String(length=16), nullable=False),
        sa.Column("path_template", sa.String(length=1024), nullable=False),
        sa.Column("operation_id", sa.String(length=255), nullable=True),
        sa.Column("summary", sa.String(length=500), nullable=False, server_default=""),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("request_schema", sa.JSON(), nullable=True),
        sa.Column("response_schema", sa.JSON(), nullable=True),
        sa.Column("auth_requirement", sa.String(length=20), nullable=False, server_default="none"),
        sa.Column("risk_level", sa.String(length=20), nullable=False, server_default="medium"),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
        sa.Column("removed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["connector_id"], ["api_connectors.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "connector_id",
            "operation_uid",
            name="uq_api_operation_tenant_connector_uid",
        ),
    )
    op.create_index(
        "idx_api_operation_tenant_connector", "api_operation_index", ["tenant_id", "connector_id"], unique=False
    )
    op.create_index("idx_api_operation_tenant_status", "api_operation_index", ["tenant_id", "status"], unique=False)
    op.create_index("idx_api_operation_tenant_method", "api_operation_index", ["tenant_id", "method"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_api_operation_tenant_method", table_name="api_operation_index")
    op.drop_index("idx_api_operation_tenant_status", table_name="api_operation_index")
    op.drop_index("idx_api_operation_tenant_connector", table_name="api_operation_index")
    op.drop_table("api_operation_index")

    op.drop_index("idx_api_connectors_tenant_status", table_name="api_connectors")
    op.drop_table("api_connectors")
