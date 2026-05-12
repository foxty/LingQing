"""Allow agent ingress endpoints without identity source until Slack is connected.

Revision ID: 071_slack_identity_nullable
Revises: 070_identity_source_hub
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "071_slack_identity_nullable"
down_revision = "070_identity_source_hub"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "agent_ingress_endpoints",
        "identity_source_id",
        existing_type=sa.Integer(),
        nullable=True,
    )


def downgrade() -> None:
    conn = op.get_bind()
    orphan_count = conn.execute(
        sa.text(
            "SELECT COUNT(*) FROM agent_ingress_endpoints WHERE identity_source_id IS NULL"
        )
    ).scalar_one()
    if orphan_count:
        raise RuntimeError(
            "Cannot downgrade: agent_ingress_endpoints rows exist without identity_source_id"
        )
    op.alter_column(
        "agent_ingress_endpoints",
        "identity_source_id",
        existing_type=sa.Integer(),
        nullable=False,
    )
