"""Identity source hub: bind_policy on sources, FKs from providers/endpoints.

Revision ID: 070_identity_source_hub
Revises: 069_ingress_identity_sources

- identity_sources.bind_policy (from auth_providers.first_login_policy / reject_unknown)
- auth_providers.identity_source_id -> identity_sources
- agent_ingress_endpoints.identity_source_id -> identity_sources
- Drop ref_type/ref_id, identity_bind_policy, first_login_policy, allowed_email_domains
"""

from __future__ import annotations

import json

import sqlalchemy as sa
from alembic import op

revision = "070_identity_source_hub"
down_revision = "069_ingress_identity_sources"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    op.add_column(
        "identity_sources",
        sa.Column(
            "bind_policy",
            sa.String(length=20),
            nullable=False,
            server_default="reject_unknown",
        ),
    )

    conn.execute(
        sa.text(
            """
            UPDATE identity_sources AS isrc
            SET bind_policy = ap.first_login_policy
            FROM auth_providers AS ap
            WHERE isrc.source_kind = 'login_provider'
              AND isrc.tenant_id = ap.tenant_id
              AND (
                (isrc.ref_type = 'auth_provider' AND isrc.ref_id = ap.id)
                OR isrc.source_key = 'oidc:' || ap.id::text
              )
            """
        )
    )

    op.add_column(
        "auth_providers",
        sa.Column("identity_source_id", sa.Integer(), nullable=True),
    )

    conn.execute(
        sa.text(
            """
            UPDATE auth_providers AS ap
            SET identity_source_id = isrc.id
            FROM identity_sources AS isrc
            WHERE isrc.tenant_id = ap.tenant_id
              AND isrc.source_kind = 'login_provider'
              AND (
                (isrc.ref_type = 'auth_provider' AND isrc.ref_id = ap.id)
                OR isrc.source_key = 'oidc:' || ap.id::text
              )
            """
        )
    )

    missing_oidc = conn.execute(
        sa.text(
            """
            SELECT ap.id, ap.tenant_id, ap.display_name, ap.first_login_policy
            FROM auth_providers AS ap
            WHERE ap.provider_type = 'oidc'
              AND ap.identity_source_id IS NULL
            """
        )
    ).fetchall()
    for provider_id, tenant_id, display_name, first_login_policy in missing_oidc:
        source_key = f"oidc:{provider_id}"
        policy = first_login_policy or "jit_create"
        result = conn.execute(
            sa.text(
                """
                INSERT INTO identity_sources
                    (tenant_id, source_kind, source_key, display_name, bind_policy)
                VALUES
                    (:tenant_id, 'login_provider', :source_key, :display_name, :bind_policy)
                RETURNING id
                """
            ),
            {
                "tenant_id": tenant_id,
                "source_key": source_key,
                "display_name": display_name,
                "bind_policy": policy,
            },
        )
        source_id = result.scalar_one()
        conn.execute(
            sa.text(
                "UPDATE auth_providers SET identity_source_id = :source_id WHERE id = :provider_id"
            ),
            {"source_id": source_id, "provider_id": provider_id},
        )

    op.alter_column("auth_providers", "identity_source_id", nullable=False)
    op.create_foreign_key(
        "auth_providers_identity_source_id_fkey",
        "auth_providers",
        "identity_sources",
        ["identity_source_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "uq_auth_providers_identity_source_id",
        "auth_providers",
        ["identity_source_id"],
        unique=True,
    )

    op.add_column(
        "agent_ingress_endpoints",
        sa.Column("identity_source_id", sa.Integer(), nullable=True),
    )

    endpoints = conn.execute(
        sa.text(
            """
            SELECT id, tenant_id, platform_config
            FROM agent_ingress_endpoints
            WHERE platform = 'slack'
            """
        )
    ).fetchall()
    for endpoint_id, tenant_id, platform_config in endpoints:
        config = platform_config if isinstance(platform_config, dict) else json.loads(platform_config or "{}")
        team_id = config.get("team_id")
        source_key = f"slack:{team_id}" if team_id else f"slack:tenant:{tenant_id}"
        source_row = conn.execute(
            sa.text(
                """
                SELECT id FROM identity_sources
                WHERE tenant_id = :tenant_id AND source_key = :source_key
                """
            ),
            {"tenant_id": tenant_id, "source_key": source_key},
        ).fetchone()
        if source_row is None:
            result = conn.execute(
                sa.text(
                    """
                    INSERT INTO identity_sources
                        (tenant_id, source_kind, source_key, display_name, bind_policy)
                    VALUES
                        (:tenant_id, 'channel_workspace', :source_key, 'Slack', 'reject_unknown')
                    RETURNING id
                    """
                ),
                {"tenant_id": tenant_id, "source_key": source_key},
            )
            source_id = result.scalar_one()
        else:
            source_id = source_row[0]
        conn.execute(
            sa.text(
                "UPDATE agent_ingress_endpoints SET identity_source_id = :source_id WHERE id = :endpoint_id"
            ),
            {"source_id": source_id, "endpoint_id": endpoint_id},
        )

    op.alter_column("agent_ingress_endpoints", "identity_source_id", nullable=False)
    op.create_foreign_key(
        "agent_ingress_endpoints_identity_source_id_fkey",
        "agent_ingress_endpoints",
        "identity_sources",
        ["identity_source_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "idx_agent_ingress_endpoints_identity_source",
        "agent_ingress_endpoints",
        ["tenant_id", "identity_source_id"],
    )

    op.drop_column("identity_sources", "ref_type")
    op.drop_column("identity_sources", "ref_id")
    op.drop_column("agent_ingress_endpoints", "identity_bind_policy")
    op.drop_column("auth_providers", "first_login_policy")
    op.drop_column("auth_providers", "allowed_email_domains")


def downgrade() -> None:
    op.add_column(
        "auth_providers",
        sa.Column(
            "allowed_email_domains",
            sa.JSON(),
            nullable=False,
            server_default="[]",
        ),
    )
    op.add_column(
        "auth_providers",
        sa.Column(
            "first_login_policy",
            sa.String(length=20),
            nullable=False,
            server_default="jit_create",
        ),
    )
    op.add_column(
        "agent_ingress_endpoints",
        sa.Column(
            "identity_bind_policy",
            sa.String(length=20),
            nullable=False,
            server_default="pending_approval",
        ),
    )
    op.add_column("identity_sources", sa.Column("ref_type", sa.String(length=30), nullable=True))
    op.add_column("identity_sources", sa.Column("ref_id", sa.Integer(), nullable=True))

    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            UPDATE auth_providers AS ap
            SET first_login_policy = isrc.bind_policy
            FROM identity_sources AS isrc
            WHERE ap.identity_source_id = isrc.id
            """
        )
    )
    conn.execute(
        sa.text(
            """
            UPDATE identity_sources AS isrc
            SET ref_type = 'auth_provider', ref_id = ap.id
            FROM auth_providers AS ap
            WHERE isrc.id = ap.identity_source_id
              AND isrc.source_kind = 'login_provider'
            """
        )
    )
    conn.execute(
        sa.text(
            """
            UPDATE identity_sources AS isrc
            SET ref_type = 'slack_workspace', ref_id = NULL
            WHERE isrc.source_kind = 'channel_workspace'
            """
        )
    )

    op.drop_index("idx_agent_ingress_endpoints_identity_source", table_name="agent_ingress_endpoints")
    op.drop_constraint(
        "agent_ingress_endpoints_identity_source_id_fkey",
        "agent_ingress_endpoints",
        type_="foreignkey",
    )
    op.drop_column("agent_ingress_endpoints", "identity_source_id")

    op.drop_index("uq_auth_providers_identity_source_id", table_name="auth_providers")
    op.drop_constraint("auth_providers_identity_source_id_fkey", "auth_providers", type_="foreignkey")
    op.drop_column("auth_providers", "identity_source_id")

    op.drop_column("identity_sources", "bind_policy")
