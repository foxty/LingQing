"""Add resource_index table and clean up legacy vector sync columns.

Revision ID: 049_resource_index_table
Revises: 048_op_doc_asset_hash_sync
Create Date: 2026-05-11
"""

import sqlalchemy as sa
from alembic import op

revision = "049_resource_index_table"
down_revision = "048_op_doc_asset_hash_sync"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Create resource_index table with all final columns
    op.create_table(
        "resource_index",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.Integer, nullable=False),
        sa.Column(
            "resource_type",
            sa.String(length=50),
            nullable=False,
            comment="document, asset, api_connector",
        ),
        sa.Column(
            "resource_id",
            sa.BigInteger,
            nullable=False,
            comment="Logical reference to resource ID",
        ),
        sa.Column(
            "owner_id",
            sa.Integer,
            nullable=False,
            comment="Resource owner user_id for ABAC/ACL filtering",
        ),
        sa.Column(
            "parent_id",
            sa.BigInteger,
            nullable=True,
            comment="Parent resource id (data_source_id for assets, connector_id for api_operations)",
        ),
        # Unified searchable content for both FTS and vector indexing
        sa.Column(
            "searchable_content",
            sa.Text,
            nullable=True,
            comment="Plain text for FTS and vector indexing",
        ),
        sa.Column(
            "vector_status",
            sa.String(length=20),
            nullable=False,
            server_default="pending",
            comment="pending/indexing/indexed/failed/stale/permanent_failed",
        ),
        sa.Column(
            "vector_content_hash",
            sa.String(length=64),
            nullable=True,
            comment="Hash of content that was successfully indexed to VectorDB",
        ),
        sa.Column(
            "vector_synced_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Last successful vector sync timestamp",
        ),
        sa.Column(
            "vector_sync_error_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Last failed vector sync timestamp",
        ),
        sa.Column(
            "vector_sync_error",
            sa.Text,
            nullable=True,
            comment="Last vector sync error message",
        ),
        sa.Column(
            "vector_retry_count",
            sa.Integer,
            nullable=False,
            server_default="0",
            comment="Number of sync retry attempts",
        ),
        sa.Column(
            "vector_next_retry_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Next allowed retry time (exponential backoff)",
        ),
        sa.Column(
            "content_updated_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Content last updated timestamp",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "resource_type",
            "resource_id",
            name="uq_resource_index_tenant_type_id",
        ),
        sa.Index(
            "idx_resource_index_tenant_vector_status",
            "tenant_id",
            "vector_status",
        ),
        sa.Index(
            "idx_resource_index_tenant_content_updated",
            "tenant_id",
            "content_updated_at",
        ),
        sa.Index(
            "idx_resource_index_owner_id",
            "owner_id",
        ),
        sa.Index(
            "idx_resource_index_parent_id",
            "parent_id",
        ),
    )

    # FTS index on searchable_content for full-text search
    # Using 'english' config for stemming support (matches 'orders' with 'order', etc.)
    op.execute("""
        ALTER TABLE resource_index
        ADD COLUMN fts_content_tsvector tsvector
            GENERATED ALWAYS AS (to_tsvector('english', COALESCE(searchable_content, ''))) STORED
    """)
    op.execute("""
        CREATE INDEX idx_resource_index_fts_content_tsvector
        ON resource_index USING gin(fts_content_tsvector)
    """)

    # 2. Drop legacy vector sync columns from documents
    op.drop_column("documents", "last_vector_synced_at")
    op.drop_column("documents", "last_vector_sync_error")
    op.drop_column("documents", "last_vector_sync_failed_at")
    op.drop_column("documents", "content_hash")
    op.drop_column("documents", "indexed_content_hash")
    op.drop_column("documents", "vector_ref_id")

    # 3. Drop legacy vector sync columns from asset_metadata
    op.drop_column("asset_metadata", "last_vector_synced_at")
    op.drop_column("asset_metadata", "last_vector_sync_error")
    op.drop_column("asset_metadata", "last_vector_sync_failed_at")
    op.drop_column("asset_metadata", "content_hash")
    op.drop_column("asset_metadata", "indexed_content_hash")

    # 4. Drop legacy vector sync columns from api_operation_index
    op.drop_column("api_operation_index", "last_vector_synced_at")
    op.drop_column("api_operation_index", "last_vector_sync_error")
    op.drop_column("api_operation_index", "last_vector_sync_failed_at")
    op.drop_column("api_operation_index", "indexed_content_hash")


def downgrade() -> None:
    # Restore legacy columns to api_operation_index
    op.add_column(
        "api_operation_index",
        sa.Column("last_vector_synced_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "api_operation_index",
        sa.Column("last_vector_sync_error", sa.Text(), nullable=True),
    )
    op.add_column(
        "api_operation_index",
        sa.Column("last_vector_sync_failed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "api_operation_index",
        sa.Column("indexed_content_hash", sa.String(length=128), nullable=True),
    )

    # Restore legacy columns to asset_metadata
    op.add_column(
        "asset_metadata",
        sa.Column("last_vector_synced_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "asset_metadata",
        sa.Column("last_vector_sync_error", sa.Text(), nullable=True),
    )
    op.add_column(
        "asset_metadata",
        sa.Column("last_vector_sync_failed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "asset_metadata",
        sa.Column("content_hash", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "asset_metadata",
        sa.Column("indexed_content_hash", sa.String(length=128), nullable=True),
    )

    # Restore legacy columns to documents
    op.add_column(
        "documents",
        sa.Column("vector_ref_id", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "documents",
        sa.Column("last_vector_synced_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "documents",
        sa.Column("last_vector_sync_error", sa.Text(), nullable=True),
    )
    op.add_column(
        "documents",
        sa.Column("last_vector_sync_failed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "documents",
        sa.Column("content_hash", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "documents",
        sa.Column("indexed_content_hash", sa.String(length=128), nullable=True),
    )

    # Drop resource_index table
    op.execute("DROP INDEX IF EXISTS idx_resource_index_fts_content_tsvector")
    op.execute("ALTER TABLE resource_index DROP COLUMN IF EXISTS fts_content_tsvector")
    op.drop_table("resource_index")