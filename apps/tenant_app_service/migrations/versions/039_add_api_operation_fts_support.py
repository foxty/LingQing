"""Add FTS support for api_operation_index.

Revision ID: 039_add_api_operation_fts
Revises: 038_api_op_vector_sync_status
Create Date: 2026-04-25
"""

from alembic import op

revision = "039_add_api_operation_fts"
down_revision = "038_api_op_vector_sync_status"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add generated search_vector and GIN index for API operation FTS."""
    op.execute("""
        ALTER TABLE api_operation_index
        ADD COLUMN search_vector tsvector
        GENERATED ALWAYS AS (
            setweight(to_tsvector('english', coalesce(operation_id, '')), 'A') ||
            setweight(to_tsvector('simple', coalesce(operation_id, '')), 'A') ||
            setweight(to_tsvector('simple', coalesce(method, '')), 'A') ||
            setweight(to_tsvector('english', coalesce(summary, '')), 'B') ||
            setweight(to_tsvector('simple', coalesce(summary, '')), 'B') ||
            setweight(to_tsvector('english', coalesce(description, '')), 'C') ||
            setweight(to_tsvector('simple', coalesce(description, '')), 'C') ||
            setweight(to_tsvector('simple', coalesce(path_template, '')), 'B') ||
            setweight(to_tsvector('simple', coalesce(tags::text, '')), 'D')
        ) STORED
    """)

    op.execute("""
        CREATE INDEX idx_api_operation_search_vector
        ON api_operation_index USING GIN(search_vector)
    """)


def downgrade() -> None:
    """Remove API operation FTS generated column and index."""
    op.execute("DROP INDEX IF EXISTS idx_api_operation_search_vector")
    op.execute("ALTER TABLE api_operation_index DROP COLUMN IF EXISTS search_vector")
