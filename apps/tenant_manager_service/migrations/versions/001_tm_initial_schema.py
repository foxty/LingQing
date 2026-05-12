"""tenant manager initial schema.

Revision ID: 001_tm_initial_schema
Revises:
Create Date: 2026-03-08 12:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "001_tm_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tenant_manager_tenants",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("tenant_uid", sa.String(length=36), nullable=False),
        sa.Column("tenant_code", sa.String(length=100), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="provisioning"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")
        ),
        sa.UniqueConstraint("tenant_uid", name="uq_tm_tenants_tenant_uid"),
        sa.UniqueConstraint("tenant_code", name="uq_tm_tenants_tenant_code"),
    )
    op.create_index("idx_tm_tenants_tenant_uid", "tenant_manager_tenants", ["tenant_uid"], unique=False)
    op.create_index("idx_tm_tenants_tenant_code", "tenant_manager_tenants", ["tenant_code"], unique=False)
    op.create_index("idx_tm_tenants_status_updated", "tenant_manager_tenants", ["status", "updated_at"], unique=False)

    op.create_table(
        "tenant_manager_lifecycle_events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("tenant_uid", sa.String(length=36), nullable=False),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column("from_status", sa.String(length=20), nullable=True),
        sa.Column("to_status", sa.String(length=20), nullable=False),
        sa.Column("reason_code", sa.String(length=50), nullable=True),
        sa.Column("operator_id", sa.String(length=100), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")
        ),
        sa.ForeignKeyConstraint(["tenant_uid"], ["tenant_manager_tenants.tenant_uid"], ondelete="CASCADE"),
    )
    op.create_index(
        "idx_tm_lifecycle_tenant_created", "tenant_manager_lifecycle_events", ["tenant_uid", "created_at"], unique=False
    )

    op.create_table(
        "tenant_manager_audit_logs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("tenant_uid", sa.String(length=36), nullable=True),
        sa.Column("actor_id", sa.String(length=100), nullable=True),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("resource_type", sa.String(length=100), nullable=False),
        sa.Column("resource_id", sa.String(length=100), nullable=False),
        sa.Column("request_id", sa.String(length=100), nullable=True),
        sa.Column("ip", sa.String(length=64), nullable=True),
        sa.Column("before_snapshot", sa.JSON(), nullable=True),
        sa.Column("after_snapshot", sa.JSON(), nullable=True),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")
        ),
    )
    op.create_index(
        "idx_tm_audit_tenant_created", "tenant_manager_audit_logs", ["tenant_uid", "created_at"], unique=False
    )
    op.create_index("idx_tm_audit_action_created", "tenant_manager_audit_logs", ["action", "created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_tm_audit_action_created", table_name="tenant_manager_audit_logs")
    op.drop_index("idx_tm_audit_tenant_created", table_name="tenant_manager_audit_logs")
    op.drop_table("tenant_manager_audit_logs")

    op.drop_index("idx_tm_lifecycle_tenant_created", table_name="tenant_manager_lifecycle_events")
    op.drop_table("tenant_manager_lifecycle_events")

    op.drop_index("idx_tm_tenants_status_updated", table_name="tenant_manager_tenants")
    op.drop_index("idx_tm_tenants_tenant_code", table_name="tenant_manager_tenants")
    op.drop_index("idx_tm_tenants_tenant_uid", table_name="tenant_manager_tenants")
    op.drop_table("tenant_manager_tenants")
