"""Backfill resource_index.parent_id for document rows.

Revision ID: 057_doc_index_parent_id
Revises: 056_document_collections
Create Date: 2026-08-31

Sets resource_index.parent_id = documents.collection_id for document resources
so FTS authz can push down collection scope via parent_id.
"""

import sqlalchemy as sa
from alembic import op

revision = "057_doc_index_parent_id"
down_revision = "056_document_collections"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE resource_index ri
            SET parent_id = d.collection_id
            FROM documents d
            WHERE ri.resource_type = 'document'
              AND ri.tenant_id = d.tenant_id
              AND ri.resource_id = d.id
              AND (ri.parent_id IS NULL OR ri.parent_id <> d.collection_id)
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE resource_index
            SET parent_id = NULL
            WHERE resource_type = 'document'
            """
        )
    )
