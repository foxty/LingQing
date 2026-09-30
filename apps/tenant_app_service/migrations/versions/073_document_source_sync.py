"""Document source sync tables (Google Drive and future providers).

Revision ID: 073_document_source_sync
Revises: 072_drop_hitl_idempotency
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "073_document_source_sync"
down_revision = "072_drop_hitl_idempotency"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "document_source_providers",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False, server_default="google_drive"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("config_json", sa.JSON(), nullable=False, server_default="{}"),
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
        sa.UniqueConstraint("tenant_id", "provider", name="uq_document_source_provider_tenant"),
    )
    op.create_index("idx_document_source_providers_tenant", "document_source_providers", ["tenant_id"])

    op.create_table(
        "document_source_oauth_states",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "provider_id",
            sa.Integer(),
            sa.ForeignKey("document_source_providers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("state", sa.String(length=128), nullable=False),
        sa.Column("code_verifier", sa.String(length=128), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.UniqueConstraint("state", name="uq_document_source_oauth_state"),
    )
    op.create_index("idx_document_source_oauth_states_expiry", "document_source_oauth_states", ["expires_at"])

    op.create_table(
        "document_source_connections",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "provider_id",
            sa.Integer(),
            sa.ForeignKey("document_source_providers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("account_email", sa.String(length=320), nullable=True),
        sa.Column("oauth_credentials_enc", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
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
        sa.UniqueConstraint("tenant_id", "owner_id", "provider_id", name="uq_document_source_connection_owner"),
    )
    op.create_index("idx_document_source_connections_tenant", "document_source_connections", ["tenant_id"])

    op.create_table(
        "document_sync_connectors",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "source_connection_id",
            sa.Integer(),
            sa.ForeignKey("document_source_connections.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "collection_id",
            sa.Integer(),
            sa.ForeignKey("document_collections.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_folder_id", sa.String(length=128), nullable=False),
        sa.Column("source_folder_name", sa.String(length=500), nullable=False),
        sa.Column("include_subfolders", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("sync_cursor", sa.String(length=256), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_sync_error", sa.Text(), nullable=True),
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
        sa.UniqueConstraint("tenant_id", "collection_id", name="uq_document_sync_connector_collection"),
        sa.UniqueConstraint(
            "source_connection_id",
            "source_folder_id",
            name="uq_document_sync_connector_folder",
        ),
    )
    op.create_index("idx_document_sync_connectors_tenant", "document_sync_connectors", ["tenant_id"])

    op.create_table(
        "document_external_files",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "connector_id",
            sa.Integer(),
            sa.ForeignKey("document_sync_connectors.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "document_id",
            sa.Integer(),
            sa.ForeignKey("documents.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("external_file_id", sa.String(length=128), nullable=False),
        sa.Column("external_modified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("external_name", sa.String(length=500), nullable=False),
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
        sa.UniqueConstraint("connector_id", "external_file_id", name="uq_document_external_file"),
    )
    op.create_index("idx_document_external_files_connector", "document_external_files", ["connector_id"])


def downgrade() -> None:
    op.drop_table("document_external_files")
    op.drop_table("document_sync_connectors")
    op.drop_table("document_source_connections")
    op.drop_table("document_source_oauth_states")
    op.drop_table("document_source_providers")
