"""Add source and sync tracking fields to api_operation_index.

Revision ID: 034_api_op_source_sync
Revises: 033_add_api_connectors
Create Date: 2026-04-21
"""

import sqlalchemy as sa
from alembic import op

revision = "034_api_op_source_sync"
down_revision = "033_add_api_connectors"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "api_operation_index",
        sa.Column("source", sa.String(length=20), nullable=False, server_default="imported"),
    )
    op.add_column(
        "api_operation_index",
        sa.Column("upstream_key", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "api_operation_index",
        sa.Column("content_hash", sa.String(length=128), nullable=True),
    )

    op.create_index(
        "idx_api_operation_tenant_connector_source",
        "api_operation_index",
        ["tenant_id", "connector_id", "source"],
        unique=False,
    )
    op.create_unique_constraint(
        "uq_api_operation_tenant_connector_source_upstream",
        "api_operation_index",
        ["tenant_id", "connector_id", "source", "upstream_key"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_api_operation_tenant_connector_source_upstream",
        "api_operation_index",
        type_="unique",
    )
    op.drop_index("idx_api_operation_tenant_connector_source", table_name="api_operation_index")

    op.drop_column("api_operation_index", "content_hash")
    op.drop_column("api_operation_index", "upstream_key")
    op.drop_column("api_operation_index", "source")
