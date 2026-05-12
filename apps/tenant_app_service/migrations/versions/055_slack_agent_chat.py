"""Slack agent chat integration schema.

Revision ID: 055_slack_agent_chat
Revises: 054_tenant_oidc_sso
Create Date: 2026-08-30

Changes:
- New tables: slack_integrations, slack_conversation_mappings, slack_processed_events
"""

import sqlalchemy as sa
from alembic import op

revision = "055_slack_agent_chat"
down_revision = "054_tenant_oidc_sso"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "slack_integrations",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "tenant_id", sa.Integer(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("slack_team_id", sa.String(length=50), nullable=True, comment="Slack workspace T..."),
        sa.Column(
            "bot_token_encrypted", sa.Text(), nullable=False, comment="Encrypted xoxb-..."
        ),
        sa.Column(
            "signing_secret_encrypted", sa.Text(), nullable=False, comment="Encrypted signing secret"
        ),
        sa.Column(
            "default_agent_id", sa.Integer(), nullable=False, server_default="-1"
        ),
        sa.Column(
            "enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")
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
        sa.UniqueConstraint("tenant_id", name="uq_slack_integration_tenant"),
    )
    op.create_index(
        "idx_slack_integrations_team_enabled", "slack_integrations", ["slack_team_id", "enabled"]
    )

    op.create_table(
        "slack_conversation_mappings",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "tenant_id", sa.Integer(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("slack_user_id", sa.String(length=50), nullable=False, comment="Slack user U..."),
        sa.Column("slack_channel_id", sa.String(length=50), nullable=False, comment="Slack channel C/D..."),
        sa.Column("thread_id", sa.String(length=255), nullable=False, comment="LingQing chat thread id"),
        sa.Column("agent_id", sa.Integer(), nullable=False, server_default="-1"),
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
            "tenant_id", "slack_user_id", "slack_channel_id", name="uq_slack_conversation_mapping"
        ),
    )
    op.create_index(
        "idx_slack_conversation_mappings_tenant", "slack_conversation_mappings", ["tenant_id"]
    )

    op.create_table(
        "slack_processed_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "tenant_id", sa.Integer(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("event_id", sa.String(length=50), nullable=False, comment="Slack event id"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.UniqueConstraint("tenant_id", "event_id", name="uq_slack_processed_event"),
    )
    op.create_index(
        "idx_slack_processed_events_created", "slack_processed_events", ["created_at"]
    )


def downgrade() -> None:
    op.drop_index("idx_slack_processed_events_created", table_name="slack_processed_events")
    op.drop_table("slack_processed_events")

    op.drop_index("idx_slack_conversation_mappings_tenant", table_name="slack_conversation_mappings")
    op.drop_table("slack_conversation_mappings")

    op.drop_index("idx_slack_integrations_team_enabled", table_name="slack_integrations")
    op.drop_table("slack_integrations")
