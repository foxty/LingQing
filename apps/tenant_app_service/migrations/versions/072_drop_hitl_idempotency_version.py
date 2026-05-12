"""Drop HITL idempotency constraint that conflicts with version bumps.

Revision ID: 072_drop_hitl_idempotency
Revises: 071_slack_identity_nullable
"""

from __future__ import annotations

from alembic import op

revision = "072_drop_hitl_idempotency"
down_revision = "071_slack_identity_nullable"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("uq_hitl_idempotency", "hitl_approvals", type_="unique")


def downgrade() -> None:
    op.create_unique_constraint(
        "uq_hitl_idempotency",
        "hitl_approvals",
        ["tenant_id", "thread_id", "tool_name", "args_hash", "version"],
    )
