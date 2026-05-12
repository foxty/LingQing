"""Drop legacy document FTS columns and normalize storage keys to tenant-relative paths.

Revision ID: 062_doc_storage_fts
Revises: 061_resource_index_parse_fields
"""

from __future__ import annotations

import json
from pathlib import Path

import sqlalchemy as sa
from alembic import op

revision = "062_doc_storage_fts"
down_revision = "061_resource_index_parse_fields"
branch_labels = None
depends_on = None


def _tenant_documents_root(tenant_id: int) -> str:
    from apps.config import get_tenant_documents_path

    return get_tenant_documents_path(tenant_id)


def _normalize_local_ref(tenant_id: int, storage_ref: str) -> str:
    if not storage_ref or storage_ref.startswith("s3://"):
        return storage_ref
    path = Path(storage_ref)
    if not path.is_absolute():
        return storage_ref.replace("\\", "/")
    tenant_root = Path(_tenant_documents_root(tenant_id))
    try:
        return path.relative_to(tenant_root).as_posix()
    except ValueError:
        return storage_ref


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_documents_tenant_search")
    op.execute("DROP INDEX IF EXISTS idx_documents_search_vector")
    op.execute("ALTER TABLE documents DROP COLUMN IF EXISTS search_vector")
    op.drop_column("documents", "preview_text")
    op.drop_column("documents", "preview_length")
    op.drop_column("documents", "total_chunks")

    bind = op.get_bind()
    documents = bind.execute(sa.text("SELECT id, tenant_id, file_url FROM documents")).fetchall()
    for doc_id, tenant_id, file_url in documents:
        if not file_url:
            continue
        normalized = _normalize_local_ref(int(tenant_id), file_url)
        if normalized != file_url:
            bind.execute(
                sa.text("UPDATE documents SET file_url = :file_url WHERE id = :id"),
                {"file_url": normalized, "id": doc_id},
            )

    index_rows = bind.execute(
        sa.text(
            "SELECT id, tenant_id, raw_content FROM resource_index "
            "WHERE resource_type = 'document' AND raw_content IS NOT NULL"
        )
    ).fetchall()
    for row_id, tenant_id, raw_content in index_rows:
        if not isinstance(raw_content, dict):
            continue
        storage_uri = raw_content.get("storage_uri")
        if not isinstance(storage_uri, str) or not storage_uri:
            continue
        normalized = _normalize_local_ref(int(tenant_id), storage_uri)
        if normalized == storage_uri:
            continue
        updated = dict(raw_content)
        updated["storage_uri"] = normalized
        bind.execute(
            sa.text("UPDATE resource_index SET raw_content = CAST(:raw_content AS JSON) WHERE id = :id"),
            {"raw_content": json.dumps(updated), "id": row_id},
        )


def downgrade() -> None:
    op.add_column("documents", sa.Column("preview_text", sa.Text(), nullable=True))
    op.add_column("documents", sa.Column("preview_length", sa.Integer(), nullable=True))
    op.add_column("documents", sa.Column("total_chunks", sa.Integer(), nullable=True))
    op.execute(
        """
        ALTER TABLE documents
        ADD COLUMN search_vector tsvector
        GENERATED ALWAYS AS (
            setweight(to_tsvector('english', coalesce(filename, '')), 'A') ||
            setweight(to_tsvector('simple', coalesce(filename, '')), 'B') ||
            setweight(to_tsvector('english', coalesce(preview_text, '')), 'C') ||
            setweight(to_tsvector('simple', coalesce(preview_text, '')), 'D')
        ) STORED
        """
    )
    op.execute("CREATE INDEX idx_documents_search_vector ON documents USING GIN(search_vector)")
    op.execute(
        """
        CREATE INDEX idx_documents_tenant_search
        ON documents(tenant_id)
        WHERE search_vector IS NOT NULL
        """
    )
