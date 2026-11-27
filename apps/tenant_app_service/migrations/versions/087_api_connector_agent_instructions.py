"""Store trusted agent instructions for installed API connector packs.

Revision ID: 087_api_connector_agent_help
Revises: 086_api_connector_pack_rules
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "087_api_connector_agent_help"
down_revision = "086_api_connector_pack_rules"
branch_labels = None
depends_on = None

SLACK_AGENT_INSTRUCTIONS = """Use this connector to search and read Slack conversations visible to the connected
user. Match the operation to the intent: keyword search, channel history, or thread
replies; resolve user, channel, and file metadata only when context is incomplete.
Bound retrieval to about 100 messages per call and at most 3 pages unless the user
requests more. Resolve Slack IDs to display names and use message permalinks for
citations. Do not send messages or change workspace settings; the bundled operations
are read-only. On missing_scope, identify the failed operation and required scope.
On empty or not-found results, explain that visibility follows the connected user's
permissions; on missing or expired credentials, ask the user to connect or reconnect
this connector.
"""


def upgrade() -> None:
    op.add_column("api_connectors", sa.Column("agent_instructions", sa.Text(), nullable=True))
    op.execute(
        sa.text(
            """
            UPDATE api_connectors
            SET agent_instructions = :instructions
            WHERE pack_ref = 'slack-user@1'
            """
        ).bindparams(instructions=SLACK_AGENT_INSTRUCTIONS)
    )


def downgrade() -> None:
    op.drop_column("api_connectors", "agent_instructions")
