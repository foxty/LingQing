"""Phase 0 native identity core tables.

Revision ID: 010_phase0_native_identity
Revises: 009_add_ds_asset_ownership
Create Date: 2026-02-04
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "010_phase0_native_identity"
down_revision = "009_add_ds_asset_ownership"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tenant_memberships",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("tenant_id", "user_id", name="uq_tenant_membership"),
    )

    op.create_table(
        "user_credentials",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("password_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("must_reset_password", sa.Boolean(), nullable=False, server_default=sa.text("false")),
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
        sa.UniqueConstraint("user_id", name="uq_user_credentials_user"),
    )

    op.create_table(
        "audit_events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    op.create_index("idx_audit_events_tenant_created", "audit_events", ["tenant_id", "created_at"])

    # Relax email uniqueness for multi-tenant usage
    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS users_email_key")

    # Backfill tenant_memberships from existing users
    op.execute(
        """
        INSERT INTO tenant_memberships (tenant_id, user_id, status, created_at)
        SELECT tenant_id, id, status, COALESCE(created_at, CURRENT_TIMESTAMP)
        FROM users
        """
    )

    # Backfill user_credentials from existing users
    op.execute(
        """
        INSERT INTO user_credentials (user_id, password_hash, created_at, updated_at)
        SELECT id, hashed_password, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        FROM users
        WHERE hashed_password IS NOT NULL
        """
    )


def downgrade() -> None:
    op.drop_index("idx_audit_events_tenant_created", table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_table("user_credentials")
    op.drop_table("tenant_memberships")

    op.create_unique_constraint("users_email_key", "users", ["email"])
