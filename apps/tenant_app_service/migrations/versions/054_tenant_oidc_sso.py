"""Tenant OIDC SSO schema.

Revision ID: 054_tenant_oidc_sso
Revises: 053_remove_report_summary
Create Date: 2026-08-25

Changes:
- Add tenants.force_sso boolean (default false)
- Add tenant_memberships.is_break_glass boolean (default false)
- New tables: auth_providers, tenant_login_domains, external_identities,
  sso_login_states, sso_login_tickets
"""

import sqlalchemy as sa
from alembic import op

revision = "054_tenant_oidc_sso"
down_revision = "053_remove_report_summary"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column(
            "force_sso",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "tenant_memberships",
        sa.Column(
            "is_break_glass",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )

    op.create_table(
        "auth_providers",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "tenant_id", sa.Integer(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("provider_type", sa.String(length=20), nullable=False, server_default="oidc"),
        sa.Column("display_name", sa.String(length=100), nullable=False),
        sa.Column(
            "enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column("config_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column(
            "allowed_email_domains", sa.JSON(), nullable=False, server_default="[]"
        ),
        sa.Column(
            "first_login_policy",
            sa.String(length=20),
            nullable=False,
            server_default="jit_create",
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
        sa.UniqueConstraint("tenant_id", "display_name", name="uq_auth_provider_tenant_display"),
    )
    op.create_index(
        "idx_auth_providers_tenant_enabled", "auth_providers", ["tenant_id", "enabled"]
    )

    op.create_table(
        "tenant_login_domains",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "tenant_id", sa.Integer(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("domain", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.UniqueConstraint("domain", name="uq_tenant_login_domain"),
    )
    op.create_index("idx_tenant_login_domains_tenant", "tenant_login_domains", ["tenant_id"])

    op.create_table(
        "external_identities",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "tenant_id", sa.Integer(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "provider_id",
            sa.Integer(),
            sa.ForeignKey("auth_providers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("external_subject", sa.String(length=255), nullable=False),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("display_name", sa.String(length=255), nullable=True),
        sa.Column(
            "status", sa.String(length=20), nullable=False, server_default="pending"
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
        sa.UniqueConstraint(
            "tenant_id", "provider_id", "external_subject", name="uq_external_identity_subject"
        ),
    )
    op.create_index(
        "idx_external_identities_tenant_user",
        "external_identities",
        ["tenant_id", "user_id"],
    )
    op.create_index(
        "idx_external_identities_tenant_status",
        "external_identities",
        ["tenant_id", "status"],
    )

    op.create_table(
        "sso_login_states",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "tenant_id", sa.Integer(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "provider_id",
            sa.Integer(),
            sa.ForeignKey("auth_providers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("state", sa.String(length=255), nullable=False),
        sa.Column("code_verifier", sa.String(length=255), nullable=False),
        sa.Column("nonce", sa.String(length=255), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "consumed", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.UniqueConstraint("state", name="uq_sso_login_state"),
    )
    op.create_index("idx_sso_login_states_expiry", "sso_login_states", ["expires_at"])

    op.create_table(
        "sso_login_tickets",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "tenant_id", sa.Integer(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("ticket", sa.String(length=255), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "consumed", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.UniqueConstraint("ticket", name="uq_sso_login_ticket"),
    )
    op.create_index("idx_sso_login_tickets_expiry", "sso_login_tickets", ["expires_at"])


def downgrade() -> None:
    op.drop_index("idx_sso_login_tickets_expiry", table_name="sso_login_tickets")
    op.drop_table("sso_login_tickets")

    op.drop_index("idx_sso_login_states_expiry", table_name="sso_login_states")
    op.drop_table("sso_login_states")

    op.drop_index("idx_external_identities_tenant_status", table_name="external_identities")
    op.drop_index("idx_external_identities_tenant_user", table_name="external_identities")
    op.drop_table("external_identities")

    op.drop_index("idx_tenant_login_domains_tenant", table_name="tenant_login_domains")
    op.drop_table("tenant_login_domains")

    op.drop_index("idx_auth_providers_tenant_enabled", table_name="auth_providers")
    op.drop_table("auth_providers")

    op.drop_column("tenant_memberships", "is_break_glass")
    op.drop_column("tenants", "force_sso")
