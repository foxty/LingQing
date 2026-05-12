"""Drop unused agent share_assigned_resources flag.

Revision ID: 067_drop_share_assigned
Revises: 066_agent_share_assigned
"""

import sqlalchemy as sa
from alembic import op

revision = "067_drop_share_assigned"
down_revision = "066_agent_share_assigned"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("acl_grants", "share_assigned_resources")


def downgrade() -> None:
    op.add_column(
        "acl_grants",
        sa.Column(
            "share_assigned_resources",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
