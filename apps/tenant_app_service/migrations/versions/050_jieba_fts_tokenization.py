"""Replace searchable_content with raw_content + tokenized_content for jieba FTS.

Revision ID: 050_jieba_fts_tokenization
Revises: 049_resource_index_table
Create Date: 2026-05-15

Changes:
- Drop old fts_content_tsvector (generated on searchable_content with 'english')
- Add raw_content (JSON) - structured content from parser
- Add tokenized_content (Text) - jieba tokenized string for FTS
- Create new fts_content_tsvector (generated on tokenized_content with 'simple')
- Drop searchable_content column
"""

import sqlalchemy as sa
from alembic import op

revision = "050_jieba_fts_tokenization"
down_revision = "049_resource_index_table"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Drop old FTS generated column and index
    op.execute("DROP INDEX IF EXISTS idx_resource_index_fts_content_tsvector")
    op.execute("ALTER TABLE resource_index DROP COLUMN IF EXISTS fts_content_tsvector")

    # 2. Add new columns
    op.add_column(
        "resource_index",
        sa.Column(
            "raw_content",
            sa.JSON,
            nullable=True,
            comment="Structured content from parser: {content, meta}",
        ),
    )
    op.add_column(
        "resource_index",
        sa.Column(
            "tokenized_content",
            sa.Text,
            nullable=True,
            comment="Jieba-tokenized content for FTS",
        ),
    )

    # 3. Create new FTS generated column on tokenized_content with 'simple' config
    # 'simple' config does no stemming, just splits on whitespace - perfect for jieba output
    op.execute("""
        ALTER TABLE resource_index
        ADD COLUMN fts_content_tsvector tsvector
            GENERATED ALWAYS AS (to_tsvector('simple', COALESCE(tokenized_content, ''))) STORED
    """)
    op.execute("""
        CREATE INDEX idx_resource_index_fts_content_tsvector
        ON resource_index USING gin(fts_content_tsvector)
    """)

    # 4. Drop old searchable_content column
    op.drop_column("resource_index", "searchable_content")


def downgrade() -> None:
    # 1. Add back searchable_content
    op.add_column(
        "resource_index",
        sa.Column(
            "searchable_content",
            sa.Text,
            nullable=True,
            comment="Plain text for FTS and vector indexing",
        ),
    )

    # 2. Drop new FTS generated column and index
    op.execute("DROP INDEX IF EXISTS idx_resource_index_fts_content_tsvector")
    op.execute("ALTER TABLE resource_index DROP COLUMN IF EXISTS fts_content_tsvector")

    # 3. Drop new columns
    op.drop_column("resource_index", "tokenized_content")
    op.drop_column("resource_index", "raw_content")

    # 4. Restore old FTS generated column with 'english' config
    op.execute("""
        ALTER TABLE resource_index
        ADD COLUMN fts_content_tsvector tsvector
            GENERATED ALWAYS AS (to_tsvector('english', COALESCE(searchable_content, ''))) STORED
    """)
    op.execute("""
        CREATE INDEX idx_resource_index_fts_content_tsvector
        ON resource_index USING gin(fts_content_tsvector)
    """)