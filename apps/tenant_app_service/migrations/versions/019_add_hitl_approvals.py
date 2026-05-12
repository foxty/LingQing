"""add hitl approvals.

Revision ID: 019_add_hitl_approvals
Revises: 018_add_rank_to_tag_values
Create Date: 2026-03-03 15:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "019_add_hitl_approvals"
down_revision = "018_add_rank_to_tag_values"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "hitl_approvals",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("thread_id", sa.String(length=255), nullable=False),
        sa.Column("session_id", sa.String(length=255), nullable=True),
        sa.Column("agent_id", sa.Integer(), nullable=False),
        sa.Column("proposal_id", sa.String(length=64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("tool_name", sa.String(length=128), nullable=False),
        sa.Column("tool_args", sa.JSON(), nullable=False),
        sa.Column("args_hash", sa.String(length=64), nullable=False),
        sa.Column("risk_level", sa.String(length=16), nullable=False),
        sa.Column("policy_snapshot", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("requested_by", sa.Integer(), nullable=False),
        sa.Column("approved_by", sa.Integer(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejected_by", sa.Integer(), nullable=True),
        sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("execution_status", sa.String(length=16), nullable=True),
        sa.Column("execution_error", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")
        ),
        sa.UniqueConstraint("tenant_id", "proposal_id", name="uq_hitl_proposal"),
        sa.UniqueConstraint("tenant_id", "thread_id", "tool_name", "args_hash", "version", name="uq_hitl_idempotency"),
    )

    op.create_index(
        "idx_hitl_pending",
        "hitl_approvals",
        ["tenant_id", "status", "expires_at"],
        unique=False,
    )
    op.create_index(
        "idx_hitl_thread",
        "hitl_approvals",
        ["tenant_id", "thread_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "idx_hitl_agent",
        "hitl_approvals",
        ["tenant_id", "agent_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_hitl_agent", table_name="hitl_approvals")
    op.drop_index("idx_hitl_thread", table_name="hitl_approvals")
    op.drop_index("idx_hitl_pending", table_name="hitl_approvals")
    op.drop_table("hitl_approvals")
