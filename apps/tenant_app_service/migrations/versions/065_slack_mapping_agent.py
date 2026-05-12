"""Scope Slack conversation mappings by agent_id.

Revision ID: 065_slack_mapping_agent
Revises: 064_agent_owner_acl
"""

from alembic import op

revision = "065_slack_mapping_agent"
down_revision = "064_agent_owner_acl"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("uq_slack_conversation_mapping", "slack_conversation_mappings", type_="unique")
    op.create_unique_constraint(
        "uq_slack_conversation_mapping",
        "slack_conversation_mappings",
        ["tenant_id", "slack_channel_id", "slack_thread_ts", "agent_id"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_slack_conversation_mapping", "slack_conversation_mappings", type_="unique")
    op.create_unique_constraint(
        "uq_slack_conversation_mapping",
        "slack_conversation_mappings",
        ["tenant_id", "slack_channel_id", "slack_thread_ts"],
    )
