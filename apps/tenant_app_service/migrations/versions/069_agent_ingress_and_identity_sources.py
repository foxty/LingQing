"""Agent ingress endpoints, identity sources, and external identity refactor.

Revision ID: 069_ingress_identity_sources
Revises: 068_drop_acl_grant_inherit

Changes:
- New tables: identity_sources, agent_ingress_endpoints, ingress_thread_links
- external_identities.provider_id -> identity_source_id
- Migrate slack_integrations / slack_conversation_mappings into new tables
- Drop slack auth_providers rows and legacy slack tables
"""

from __future__ import annotations

import json
import secrets

import sqlalchemy as sa
from alembic import op

revision = "069_ingress_identity_sources"
down_revision = "068_drop_acl_grant_inherit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "identity_sources",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "tenant_id", sa.Integer(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("source_kind", sa.String(length=30), nullable=False),
        sa.Column("source_key", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=100), nullable=False),
        sa.Column("ref_type", sa.String(length=30), nullable=True),
        sa.Column("ref_id", sa.Integer(), nullable=True),
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
        sa.UniqueConstraint("tenant_id", "source_key", name="uq_identity_source_tenant_key"),
    )
    op.create_index(
        "idx_identity_sources_tenant_kind", "identity_sources", ["tenant_id", "source_kind"]
    )

    op.create_table(
        "agent_ingress_endpoints",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "tenant_id", sa.Integer(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("agent_id", sa.Integer(), nullable=False),
        sa.Column("platform", sa.String(length=20), nullable=False, server_default="slack"),
        sa.Column("endpoint_key", sa.String(length=64), nullable=False),
        sa.Column("external_scope_key", sa.String(length=255), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "identity_bind_policy",
            sa.String(length=20),
            nullable=False,
            server_default="pending_approval",
        ),
        sa.Column("platform_config", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("credentials_encrypted", sa.JSON(), nullable=False, server_default="{}"),
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
        sa.UniqueConstraint("tenant_id", "agent_id", "platform", name="uq_agent_ingress_endpoint"),
        sa.UniqueConstraint("endpoint_key", name="uq_agent_ingress_endpoint_key"),
    )
    op.create_index(
        "idx_agent_ingress_endpoints_tenant_platform",
        "agent_ingress_endpoints",
        ["tenant_id", "platform", "enabled"],
    )

    op.create_table(
        "ingress_thread_links",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "tenant_id", sa.Integer(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "endpoint_id",
            sa.Integer(),
            sa.ForeignKey("agent_ingress_endpoints.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("agent_id", sa.Integer(), nullable=False),
        sa.Column("external_user_id", sa.String(length=50), nullable=False),
        sa.Column("external_channel_id", sa.String(length=50), nullable=False),
        sa.Column("external_thread_key", sa.String(length=50), nullable=False, server_default=""),
        sa.Column("chat_thread_id", sa.String(length=255), nullable=False),
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
            "endpoint_id",
            "external_channel_id",
            "external_thread_key",
            name="uq_ingress_thread_link",
        ),
    )
    op.create_index("idx_ingress_thread_links_tenant", "ingress_thread_links", ["tenant_id"])
    op.create_index("idx_ingress_thread_links_thread", "ingress_thread_links", ["chat_thread_id"])

    conn = op.get_bind()

    oidc_providers = conn.execute(
        sa.text("SELECT id, tenant_id, display_name FROM auth_providers WHERE provider_type = 'oidc'")
    ).fetchall()
    oidc_source_map: dict[int, int] = {}
    for provider_id, tenant_id, display_name in oidc_providers:
        source_key = f"oidc:{provider_id}"
        result = conn.execute(
            sa.text(
                """
                INSERT INTO identity_sources
                    (tenant_id, source_kind, source_key, display_name, ref_type, ref_id)
                VALUES
                    (:tenant_id, 'login_provider', :source_key, :display_name, 'auth_provider', :ref_id)
                RETURNING id
                """
            ),
            {
                "tenant_id": tenant_id,
                "source_key": source_key,
                "display_name": display_name,
                "ref_id": provider_id,
            },
        )
        oidc_source_map[provider_id] = result.scalar_one()

    slack_integrations = conn.execute(
        sa.text("SELECT tenant_id, slack_team_id FROM slack_integrations")
    ).fetchall()
    slack_source_by_tenant: dict[int, int] = {}
    for tenant_id, team_id in slack_integrations:
        scope = team_id or f"tenant:{tenant_id}"
        source_key = f"slack:{scope}"
        result = conn.execute(
            sa.text(
                """
                INSERT INTO identity_sources
                    (tenant_id, source_kind, source_key, display_name, ref_type, ref_id)
                VALUES
                    (:tenant_id, 'channel_workspace', :source_key, 'Slack', 'slack_workspace', NULL)
                RETURNING id
                """
            ),
            {"tenant_id": tenant_id, "source_key": source_key},
        )
        slack_source_by_tenant[tenant_id] = result.scalar_one()

    slack_providers = conn.execute(
        sa.text("SELECT id, tenant_id FROM auth_providers WHERE provider_type = 'slack'")
    ).fetchall()
    slack_provider_source_map: dict[int, int] = {}
    for provider_id, tenant_id in slack_providers:
        if tenant_id not in slack_source_by_tenant:
            source_key = f"slack:tenant:{tenant_id}"
            result = conn.execute(
                sa.text(
                    """
                    INSERT INTO identity_sources
                        (tenant_id, source_kind, source_key, display_name, ref_type, ref_id)
                    VALUES
                        (:tenant_id, 'channel_workspace', :source_key, 'Slack', 'slack_workspace', NULL)
                    RETURNING id
                    """
                ),
                {"tenant_id": tenant_id, "source_key": source_key},
            )
            slack_source_by_tenant[tenant_id] = result.scalar_one()
        slack_provider_source_map[provider_id] = slack_source_by_tenant[tenant_id]

    op.add_column(
        "external_identities",
        sa.Column("identity_source_id", sa.Integer(), nullable=True),
    )
    identities = conn.execute(sa.text("SELECT id, provider_id FROM external_identities")).fetchall()
    for identity_id, provider_id in identities:
        provider_type = conn.execute(
            sa.text("SELECT provider_type FROM auth_providers WHERE id = :id"),
            {"id": provider_id},
        ).scalar_one_or_none()
        if provider_type == "oidc":
            source_id = oidc_source_map.get(provider_id)
        elif provider_type == "slack":
            source_id = slack_provider_source_map.get(provider_id)
        else:
            source_id = None
        if source_id is None:
            continue
        conn.execute(
            sa.text("UPDATE external_identities SET identity_source_id = :source_id WHERE id = :id"),
            {"source_id": source_id, "id": identity_id},
        )

    op.drop_constraint("uq_external_identity_subject", "external_identities", type_="unique")
    op.drop_constraint(
        "external_identities_provider_id_fkey", "external_identities", type_="foreignkey"
    )
    op.drop_column("external_identities", "provider_id")
    op.alter_column("external_identities", "identity_source_id", nullable=False)
    op.create_foreign_key(
        "external_identities_identity_source_id_fkey",
        "external_identities",
        "identity_sources",
        ["identity_source_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_unique_constraint(
        "uq_external_identity_subject",
        "external_identities",
        ["tenant_id", "identity_source_id", "external_subject"],
    )

    integrations = conn.execute(
        sa.text(
            """
            SELECT tenant_id, slack_team_id, bot_token_encrypted, signing_secret_encrypted,
                   default_agent_id, enabled
            FROM slack_integrations
            """
        )
    ).fetchall()
    for tenant_id, team_id, bot_token, signing_secret, agent_id, enabled in integrations:
        endpoint_key = secrets.token_urlsafe(32)
        scope = team_id or f"tenant:{tenant_id}"
        external_scope_key = f"slack:{scope}"
        platform_config_json = json.dumps({"team_id": team_id} if team_id else {})
        credentials_json = json.dumps({"bot_token": bot_token, "signing_secret": signing_secret})
        conn.execute(
            sa.text(
                """
                INSERT INTO agent_ingress_endpoints
                    (tenant_id, agent_id, platform, endpoint_key, external_scope_key, enabled,
                     identity_bind_policy, platform_config, credentials_encrypted)
                VALUES
                    (:tenant_id, :agent_id, 'slack', :endpoint_key, :external_scope_key, :enabled,
                     'pending_approval', CAST(:platform_config AS JSON), CAST(:credentials AS JSON))
                """
            ),
            {
                "tenant_id": tenant_id,
                "agent_id": agent_id,
                "endpoint_key": endpoint_key,
                "external_scope_key": external_scope_key,
                "enabled": enabled,
                "platform_config": platform_config_json,
                "credentials": credentials_json,
            },
        )

    mappings = conn.execute(
        sa.text(
            """
            SELECT tenant_id, slack_user_id, slack_channel_id, slack_thread_ts, thread_id, agent_id
            FROM slack_conversation_mappings
            """
        )
    ).fetchall()
    for tenant_id, user_id, channel_id, thread_ts, thread_id, agent_id in mappings:
        endpoint_id = conn.execute(
            sa.text(
                """
                SELECT id FROM agent_ingress_endpoints
                WHERE tenant_id = :tenant_id AND agent_id = :agent_id AND platform = 'slack'
                LIMIT 1
                """
            ),
            {"tenant_id": tenant_id, "agent_id": agent_id},
        ).scalar_one_or_none()
        if endpoint_id is None:
            endpoint_id = conn.execute(
                sa.text(
                    """
                    SELECT id FROM agent_ingress_endpoints
                    WHERE tenant_id = :tenant_id AND platform = 'slack'
                    LIMIT 1
                    """
                ),
                {"tenant_id": tenant_id},
            ).scalar_one_or_none()
        if endpoint_id is None:
            continue
        conn.execute(
            sa.text(
                """
                INSERT INTO ingress_thread_links
                    (tenant_id, endpoint_id, agent_id, external_user_id, external_channel_id,
                     external_thread_key, chat_thread_id)
                VALUES
                    (:tenant_id, :endpoint_id, :agent_id, :user_id, :channel_id, :thread_key, :thread_id)
                ON CONFLICT DO NOTHING
                """
            ),
            {
                "tenant_id": tenant_id,
                "endpoint_id": endpoint_id,
                "agent_id": agent_id,
                "user_id": user_id,
                "channel_id": channel_id,
                "thread_key": thread_ts or "",
                "thread_id": thread_id,
            },
        )

    op.drop_index("idx_slack_conversation_mappings_tenant", table_name="slack_conversation_mappings")
    op.drop_table("slack_conversation_mappings")
    op.drop_index("idx_slack_integrations_team_enabled", table_name="slack_integrations")
    op.drop_table("slack_integrations")

    conn.execute(sa.text("DELETE FROM auth_providers WHERE provider_type = 'slack'"))


def downgrade() -> None:
    raise NotImplementedError("Downgrade not supported for ingress refactor")
