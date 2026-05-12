"""Add FTS support for documents and asset_metadata.

Revision ID: 007_add_fts_support
Revises: 006_rm_artifact_id
Create Date: 2026-01-28
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "007_add_fts_support"
down_revision = "006_rm_artifact_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add FTS support to documents and asset_metadata tables."""
    # ========== Documents Table ==========

    # Add preview_text column for storing first N chunks
    op.add_column("documents", sa.Column("preview_text", sa.Text, nullable=True))
    op.add_column("documents", sa.Column("preview_length", sa.Integer, nullable=True))
    op.add_column("documents", sa.Column("total_chunks", sa.Integer, nullable=True))

    # Add FTS vector column (generated from filename + preview_text)
    # Multi-language support:
    # - 'english': Stemming for English words (revenue → revenu)
    # - 'simple': Exact tokenization for Chinese, numbers, special chars
    # Weight hierarchy: filename (A,B) > preview content (C,D)
    op.execute("""
        ALTER TABLE documents 
        ADD COLUMN search_vector tsvector 
        GENERATED ALWAYS AS (
            setweight(to_tsvector('english', coalesce(filename, '')), 'A') ||
            setweight(to_tsvector('simple', coalesce(filename, '')), 'B') ||
            setweight(to_tsvector('english', coalesce(preview_text, '')), 'C') ||
            setweight(to_tsvector('simple', coalesce(preview_text, '')), 'D')
        ) STORED
    """)

    # Create GIN index for fast FTS
    op.execute("CREATE INDEX idx_documents_search_vector ON documents USING GIN(search_vector)")

    # Create composite index for tenant-scoped search
    op.execute("""
        CREATE INDEX idx_documents_tenant_search 
        ON documents(tenant_id) 
        WHERE search_vector IS NOT NULL
    """)

    # ========== Asset Metadata Table ==========

    # Add FTS vector column (generated from asset_name + description + columns)
    # Multi-language support for table/column names and descriptions
    # Weight hierarchy: asset_name (A) > description (B) > columns (C)
    op.execute("""
        ALTER TABLE asset_metadata 
        ADD COLUMN search_vector tsvector 
        GENERATED ALWAYS AS (
            setweight(to_tsvector('english', coalesce(asset_name, '')), 'A') ||
            setweight(to_tsvector('simple', coalesce(asset_name, '')), 'A') ||
            setweight(to_tsvector('english', coalesce(description, '')), 'B') ||
            setweight(to_tsvector('simple', coalesce(description, '')), 'B') ||
            setweight(to_tsvector('simple', coalesce(columns::text, '')), 'C')
        ) STORED
    """)

    # Create GIN index for fast FTS
    op.execute("CREATE INDEX idx_asset_metadata_search_vector ON asset_metadata USING GIN(search_vector)")

    # Create composite index for data_source scoped search
    op.execute("""
        CREATE INDEX idx_asset_metadata_datasource_search 
        ON asset_metadata(data_source_id) 
        WHERE search_vector IS NOT NULL
    """)


def downgrade() -> None:
    """Remove FTS support."""
    # Documents
    op.execute("DROP INDEX IF EXISTS idx_documents_tenant_search")
    op.execute("DROP INDEX IF EXISTS idx_documents_search_vector")
    op.execute("ALTER TABLE documents DROP COLUMN IF EXISTS search_vector")
    op.drop_column("documents", "total_chunks")
    op.drop_column("documents", "preview_length")
    op.drop_column("documents", "preview_text")

    # Asset Metadata
    op.execute("DROP INDEX IF EXISTS idx_asset_metadata_datasource_search")
    op.execute("DROP INDEX IF EXISTS idx_asset_metadata_search_vector")
    op.execute("ALTER TABLE asset_metadata DROP COLUMN IF EXISTS search_vector")
