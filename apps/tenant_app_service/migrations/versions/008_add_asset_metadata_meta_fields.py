"""Add meta fields to asset_metadata and update FTS vector.

Revision ID: 008_add_asset_metadata_meta_fields
Revises: 007_add_fts_support
Create Date: 2026-01-31
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "008_asset_meta_fields"
down_revision = "007_add_fts_support"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("asset_metadata", sa.Column("meta", sa.JSON(), nullable=True))
    op.add_column("asset_metadata", sa.Column("meta_override", sa.JSON(), nullable=True))

    op.execute("DROP INDEX IF EXISTS idx_asset_metadata_datasource_search")
    op.execute("DROP INDEX IF EXISTS idx_asset_metadata_search_vector")
    op.execute("ALTER TABLE asset_metadata DROP COLUMN IF EXISTS search_vector")
    op.drop_column("asset_metadata", "description")

    op.execute(
        """
        ALTER TABLE asset_metadata
        ADD COLUMN search_vector tsvector
        GENERATED ALWAYS AS (
            setweight(to_tsvector('english', coalesce(asset_name, '')), 'A') ||
            setweight(to_tsvector('simple', coalesce(asset_name, '')), 'A') ||
            setweight(
                to_tsvector(
                    'english',
                    coalesce(meta_override->>'description', meta->>'description', '')
                ),
                'B'
            ) ||
            setweight(
                to_tsvector(
                    'simple',
                    coalesce(meta_override->>'description', meta->>'description', '')
                ),
                'B'
            ) ||
            setweight(
                to_tsvector(
                    'simple',
                    coalesce(
                        (
                            coalesce((meta->'column_description')::jsonb, '{}'::jsonb) ||
                            coalesce((meta_override->'column_description')::jsonb, '{}'::jsonb)
                        )::text,
                        ''
                    )
                ),
                'C'
            ) ||
            setweight(to_tsvector('simple', coalesce(columns::text, '')), 'C')
        ) STORED
        """
    )

    op.execute("CREATE INDEX idx_asset_metadata_search_vector ON asset_metadata USING GIN(search_vector)")
    op.execute(
        """
        CREATE INDEX idx_asset_metadata_datasource_search
        ON asset_metadata(data_source_id)
        WHERE search_vector IS NOT NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_asset_metadata_datasource_search")
    op.execute("DROP INDEX IF EXISTS idx_asset_metadata_search_vector")
    op.execute("ALTER TABLE asset_metadata DROP COLUMN IF EXISTS search_vector")
    op.add_column("asset_metadata", sa.Column("description", sa.Text(), nullable=True))

    op.execute(
        """
        ALTER TABLE asset_metadata
        ADD COLUMN search_vector tsvector
        GENERATED ALWAYS AS (
            setweight(to_tsvector('english', coalesce(asset_name, '')), 'A') ||
            setweight(to_tsvector('simple', coalesce(asset_name, '')), 'A') ||
            setweight(to_tsvector('english', coalesce(description, '')), 'B') ||
            setweight(to_tsvector('simple', coalesce(description, '')), 'B') ||
            setweight(to_tsvector('simple', coalesce(columns::text, '')), 'C')
        ) STORED
        """
    )

    op.execute("CREATE INDEX idx_asset_metadata_search_vector ON asset_metadata USING GIN(search_vector)")
    op.execute(
        """
        CREATE INDEX idx_asset_metadata_datasource_search
        ON asset_metadata(data_source_id)
        WHERE search_vector IS NOT NULL
        """
    )

    op.drop_column("asset_metadata", "meta_override")
    op.drop_column("asset_metadata", "meta")
