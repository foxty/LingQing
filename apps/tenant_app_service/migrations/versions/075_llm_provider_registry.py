"""Add llm_providers and llm_model_profiles tables.

Revision ID: 075_llm_provider_registry
Revises: 074_drop_task_source_type
Create Date: 2026-10-02
"""

import sqlalchemy as sa
from alembic import op

revision = "075_llm_provider_registry"
down_revision = "074_drop_task_source_type"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "llm_providers",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("display_name", sa.String(length=100), nullable=False),
        sa.Column("preset_key", sa.String(length=64), nullable=True),
        sa.Column("type", sa.String(length=32), nullable=False, server_default="openai-compatible"),
        sa.Column("api_base", sa.String(length=1024), nullable=False),
        sa.Column("embedding_api_base", sa.String(length=1024), nullable=True),
        sa.Column("api_key_encrypted", sa.Text(), nullable=False),
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
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "display_name", name="uq_llm_providers_tenant_display_name"),
    )
    op.create_index("idx_llm_providers_tenant_status", "llm_providers", ["tenant_id", "status"], unique=False)

    op.create_table(
        "llm_model_profiles",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("provider_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("category", sa.String(length=20), nullable=False),
        sa.Column("model_id", sa.String(length=255), nullable=False),
        sa.Column("params", sa.JSON(), nullable=True),
        sa.Column("catalog_model_key", sa.String(length=128), nullable=True),
        sa.Column("source", sa.String(length=20), nullable=False, server_default="preset"),
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
        sa.CheckConstraint("category IN ('llm', 'embedding')", name="ck_llm_model_profiles_category"),
        sa.CheckConstraint("source IN ('preset', 'custom')", name="ck_llm_model_profiles_source"),
        sa.ForeignKeyConstraint(["provider_id"], ["llm_providers.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "name", name="uq_llm_model_profiles_tenant_name"),
    )
    op.create_index(
        "idx_llm_model_profiles_tenant_category",
        "llm_model_profiles",
        ["tenant_id", "category"],
        unique=False,
    )
    op.create_index("idx_llm_model_profiles_provider", "llm_model_profiles", ["provider_id"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_llm_model_profiles_provider", table_name="llm_model_profiles")
    op.drop_index("idx_llm_model_profiles_tenant_category", table_name="llm_model_profiles")
    op.drop_table("llm_model_profiles")
    op.drop_index("idx_llm_providers_tenant_status", table_name="llm_providers")
    op.drop_table("llm_providers")
