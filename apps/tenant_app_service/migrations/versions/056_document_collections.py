"""Add document collections and collection-scoped document authz.

Revision ID: 056_document_collections
Revises: 055_slack_agent_chat
Create Date: 2026-08-30

Changes:
- New table: document_collections
- documents.collection_id FK (required after backfill)
- Dedup constraint: (tenant_id, collection_id, file_hash)
- Archive document-level ACL rows
"""

import sqlalchemy as sa
from alembic import op

revision = "056_document_collections"
down_revision = "055_slack_agent_chat"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "document_collections",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "tenant_id",
            sa.Integer(),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "owner_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=False,
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
        sa.UniqueConstraint("tenant_id", "name", name="uq_document_collection_tenant_name"),
    )
    op.create_index("ix_document_collections_tenant_id", "document_collections", ["tenant_id"])
    op.create_index("ix_document_collections_owner_id", "document_collections", ["owner_id"])

    op.add_column(
        "documents",
        sa.Column(
            "collection_id",
            sa.Integer(),
            sa.ForeignKey("document_collections.id", ondelete="RESTRICT"),
            nullable=True,
        ),
    )

    # Seed default "General" collection per tenant and backfill documents.
    op.execute(
        sa.text(
            """
            INSERT INTO document_collections (tenant_id, name, description, owner_id, created_at, updated_at)
            SELECT
                t.id,
                'General',
                'Default document collection',
                COALESCE(
                    (
                        SELECT d.owner_id
                        FROM documents d
                        WHERE d.tenant_id = t.id AND d.owner_id IS NOT NULL
                        ORDER BY d.id
                        LIMIT 1
                    ),
                    (
                        SELECT tm.user_id
                        FROM tenant_memberships tm
                        WHERE tm.tenant_id = t.id AND tm.status = 'active'
                        ORDER BY tm.id
                        LIMIT 1
                    ),
                    1
                ),
                CURRENT_TIMESTAMP,
                CURRENT_TIMESTAMP
            FROM tenants t
            """
        )
    )

    op.execute(
        sa.text(
            """
            UPDATE documents d
            SET collection_id = dc.id
            FROM document_collections dc
            WHERE dc.tenant_id = d.tenant_id
              AND dc.name = 'General'
              AND d.collection_id IS NULL
            """
        )
    )

    op.alter_column("documents", "collection_id", nullable=False)
    op.create_index("ix_documents_collection_id", "documents", ["collection_id"])

    op.drop_constraint("uq_document_tenant_owner_hash", "documents", type_="unique")
    op.create_unique_constraint(
        "uq_document_tenant_collection_hash",
        "documents",
        ["tenant_id", "collection_id", "file_hash"],
    )

    # Remove document-level ACL shares; collections become the permission boundary.
    op.execute(sa.text("DELETE FROM acl_grants WHERE resource_type = 'document'"))
    op.execute(sa.text("DELETE FROM resource_acl WHERE resource_type = 'document'"))


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM acl_grants WHERE resource_type = 'document_collection'"))
    op.execute(sa.text("DELETE FROM resource_acl WHERE resource_type = 'document_collection'"))

    op.drop_constraint("uq_document_tenant_collection_hash", "documents", type_="unique")
    op.create_unique_constraint(
        "uq_document_tenant_owner_hash",
        "documents",
        ["tenant_id", "owner_id", "file_hash"],
    )

    op.drop_index("ix_documents_collection_id", "documents")
    op.drop_column("documents", "collection_id")

    op.drop_index("ix_document_collections_owner_id", "document_collections")
    op.drop_index("ix_document_collections_tenant_id", "document_collections")
    op.drop_table("document_collections")
