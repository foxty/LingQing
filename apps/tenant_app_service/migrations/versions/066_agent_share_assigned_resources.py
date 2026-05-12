"""Store agent share-assigned-resources on the agent grant.

Revision ID: 066_agent_share_assigned
Revises: 065_slack_mapping_agent
"""

import sqlalchemy as sa
from alembic import op

revision = "066_agent_share_assigned"
down_revision = "065_slack_mapping_agent"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "acl_grants",
        sa.Column(
            "share_assigned_resources",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.execute("DELETE FROM acl_grants WHERE inherit_from_type = 'agent'")


def downgrade() -> None:
    op.drop_column("acl_grants", "share_assigned_resources")
