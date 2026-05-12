"""Tag system and ABAC core tables.

Revision ID: 011_tag_system_and_abac
Revises: 010_phase0_native_identity
Create Date: 2026-02-08
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "011_tag_system_and_abac"
down_revision = "010_phase0_native_identity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tag_keys",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("type", sa.String(length=20), nullable=False),
        sa.Column("allowed_values", sa.JSON(), nullable=True),
        sa.Column("value_mode", sa.String(length=20), nullable=False),
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
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.UniqueConstraint("tenant_id", "name", name="uq_tag_keys_tenant_name"),
    )
    op.create_index("idx_tag_keys_tenant", "tag_keys", ["tenant_id"])
    op.create_index("idx_tag_keys_status", "tag_keys", ["tenant_id", "status"])

    op.create_table(
        "tag_values",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("key_id", sa.BigInteger(), sa.ForeignKey("tag_keys.id", ondelete="CASCADE"), nullable=False),
        sa.Column("value", sa.String(length=200), nullable=False),
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
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.UniqueConstraint("tenant_id", "key_id", "value", name="uq_tag_values_tenant_key_value"),
    )
    op.create_index("idx_tag_values_tenant", "tag_values", ["tenant_id"])
    op.create_index("idx_tag_values_key", "tag_values", ["tenant_id", "key_id"])
    op.create_index("idx_tag_values_status", "tag_values", ["tenant_id", "status"])

    op.create_table(
        "tag_bindings",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("resource_type", sa.String(length=50), nullable=False),
        sa.Column("resource_id", sa.BigInteger(), nullable=False),
        sa.Column("tag_value_id", sa.BigInteger(), sa.ForeignKey("tag_values.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.UniqueConstraint(
            "tenant_id",
            "resource_type",
            "resource_id",
            "tag_value_id",
            name="uq_tag_bindings_tenant_resource_tag_value",
        ),
    )
    op.create_index("idx_tag_bindings_resource", "tag_bindings", ["tenant_id", "resource_type", "resource_id"])
    op.create_index("idx_tag_bindings_tag_value", "tag_bindings", ["tenant_id", "tag_value_id"])

    op.create_table(
        "resource_tag_configs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("resource_type", sa.String(length=50), nullable=False),
        sa.Column("tag_key_id", sa.BigInteger(), sa.ForeignKey("tag_keys.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.UniqueConstraint(
            "tenant_id",
            "resource_type",
            "tag_key_id",
            name="uq_resource_tag_configs_tenant_resource_key",
        ),
    )
    op.create_index(
        "idx_resource_tag_configs_resource",
        "resource_tag_configs",
        ["tenant_id", "resource_type"],
    )

    op.create_table(
        "abac_policies",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("resource_type", sa.String(length=50), nullable=False),
        sa.Column("expression", sa.JSON(), nullable=False),
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
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
    )
    op.create_index("idx_abac_policies_tenant", "abac_policies", ["tenant_id"])
    op.create_index(
        "idx_abac_policies_resource_type",
        "abac_policies",
        ["tenant_id", "resource_type", "status"],
    )


def downgrade() -> None:
    op.drop_index("idx_abac_policies_resource_type", table_name="abac_policies")
    op.drop_index("idx_abac_policies_tenant", table_name="abac_policies")
    op.drop_table("abac_policies")

    op.drop_index("idx_resource_tag_configs_resource", table_name="resource_tag_configs")
    op.drop_table("resource_tag_configs")

    op.drop_index("idx_tag_bindings_tag_value", table_name="tag_bindings")
    op.drop_index("idx_tag_bindings_resource", table_name="tag_bindings")
    op.drop_table("tag_bindings")

    op.drop_index("idx_tag_values_status", table_name="tag_values")
    op.drop_index("idx_tag_values_key", table_name="tag_values")
    op.drop_index("idx_tag_values_tenant", table_name="tag_values")
    op.drop_table("tag_values")

    op.drop_index("idx_tag_keys_status", table_name="tag_keys")
    op.drop_index("idx_tag_keys_tenant", table_name="tag_keys")
    op.drop_table("tag_keys")
