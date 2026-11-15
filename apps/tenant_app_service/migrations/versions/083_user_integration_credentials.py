"""BYOT user integration credentials and credential_mode on external integrations.

Revision ID: 083_user_integration_credentials
Revises: 082_slack_msg_dedupe
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "083_user_integration_credentials"
down_revision = "082_slack_msg_dedupe"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "data_sources",
        sa.Column(
            "credential_mode",
            sa.String(length=20),
            nullable=False,
            server_default="shared",
        ),
    )
    op.add_column(
        "api_connectors",
        sa.Column(
            "credential_mode",
            sa.String(length=20),
            nullable=False,
            server_default="shared",
        ),
    )

    op.create_table(
        "user_integration_credentials",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "tenant_id",
            sa.Integer(),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("resource_type", sa.String(length=32), nullable=False),
        sa.Column("resource_id", sa.Integer(), nullable=False),
        sa.Column("auth_type", sa.String(length=50), nullable=False, server_default="bearer"),
        sa.Column("secrets_enc", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("account_label", sa.String(length=320), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
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
            "tenant_id",
            "user_id",
            "resource_type",
            "resource_id",
            name="uq_user_integration_cred",
        ),
    )
    op.create_index(
        "idx_user_integration_cred_resource",
        "user_integration_credentials",
        ["tenant_id", "resource_type", "resource_id"],
    )
    op.create_index(
        "idx_user_integration_cred_user",
        "user_integration_credentials",
        ["tenant_id", "user_id"],
    )


def downgrade() -> None:
    op.drop_index("idx_user_integration_cred_user", table_name="user_integration_credentials")
    op.drop_index("idx_user_integration_cred_resource", table_name="user_integration_credentials")
    op.drop_table("user_integration_credentials")
    op.drop_column("api_connectors", "credential_mode")
    op.drop_column("data_sources", "credential_mode")
