"""Add message_feedbacks table for AI turn ratings.

Revision ID: 076_add_message_feedback
Revises: 075_llm_provider_registry
Create Date: 2026-10-05
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "076_add_message_feedback"
down_revision = "075_llm_provider_registry"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "message_feedbacks",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("thread_id", sa.String(length=255), nullable=False),
        sa.Column("session_id", sa.String(length=255), nullable=True),
        sa.Column("message_id", sa.String(length=255), nullable=False),
        sa.Column("agent_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("rating", sa.String(length=16), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("source", sa.String(length=16), nullable=False, server_default="portal"),
        sa.Column("external_ref", sa.JSON(), nullable=True),
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
        sa.UniqueConstraint("tenant_id", "message_id", "user_id", name="uq_message_feedbacks_user_message"),
    )
    op.create_index("idx_message_feedbacks_tenant_created", "message_feedbacks", ["tenant_id", "created_at"])
    op.create_index("idx_message_feedbacks_tenant_agent", "message_feedbacks", ["tenant_id", "agent_id", "created_at"])
    op.create_index("idx_message_feedbacks_thread", "message_feedbacks", ["tenant_id", "thread_id"])


def downgrade() -> None:
    # Plural names (current) and singular names (first 076 apply before rename).
    for index_name in (
        "idx_message_feedbacks_thread",
        "idx_message_feedbacks_tenant_agent",
        "idx_message_feedbacks_tenant_created",
        "idx_message_feedback_thread",
        "idx_message_feedback_tenant_agent",
        "idx_message_feedback_tenant_created",
    ):
        op.execute(f"DROP INDEX IF EXISTS {index_name}")

    op.execute("DROP TABLE IF EXISTS message_feedbacks")
    op.execute("DROP TABLE IF EXISTS message_feedback")
