"""Add slack_thread_ts to conversation mappings for channel/group chat.

Revision ID: 060_slack_channel_thread_mapping
Revises: 059_drop_asset_legacy_authz
Create Date: 2026-09-01

Changes:
- slack_conversation_mappings.slack_thread_ts column
- unique key becomes (tenant_id, slack_channel_id, slack_thread_ts)
"""

import sqlalchemy as sa
from alembic import op

revision = "060_slack_channel_thread_mapping"
down_revision = "059_drop_asset_legacy_authz"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "slack_conversation_mappings",
        sa.Column(
            "slack_thread_ts",
            sa.String(length=50),
            nullable=False,
            server_default="",
            comment="Slack thread root ts; empty for DMs",
        ),
    )
    op.drop_constraint("uq_slack_conversation_mapping", "slack_conversation_mappings", type_="unique")
    op.create_unique_constraint(
        "uq_slack_conversation_mapping",
        "slack_conversation_mappings",
        ["tenant_id", "slack_channel_id", "slack_thread_ts"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_slack_conversation_mapping", "slack_conversation_mappings", type_="unique")
    op.create_unique_constraint(
        "uq_slack_conversation_mapping",
        "slack_conversation_mappings",
        ["tenant_id", "slack_user_id", "slack_channel_id"],
    )
    op.drop_column("slack_conversation_mappings", "slack_thread_ts")
