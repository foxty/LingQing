"""Cumulative thread watermark and in-run agent summaries.

Revision ID: 081_agent_run_summaries
Revises: 080_parser_default_to_docling
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "081_agent_run_summaries"
down_revision = "080_parser_default_to_docling"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "thread_summaries",
        sa.Column("through_trigger_message_id", sa.String(length=255), nullable=True),
    )
    op.create_table(
        "agent_run_summaries",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("thread_id", sa.String(length=255), nullable=False),
        sa.Column("summary_text", sa.Text(), nullable=False),
        sa.Column("cutoff_message_id", sa.String(length=255), nullable=True),
        sa.Column("through_agent_run_message_id", sa.Integer(), nullable=True),
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
        sa.ForeignKeyConstraint(["run_id"], ["agent_runs.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("run_id", name="uq_agent_run_summaries_run_id"),
    )
    op.create_index("idx_agent_run_summaries_tenant", "agent_run_summaries", ["tenant_id"])
    op.create_index("idx_agent_run_summaries_thread", "agent_run_summaries", ["thread_id", "updated_at"])


def downgrade() -> None:
    op.drop_index("idx_agent_run_summaries_thread", table_name="agent_run_summaries")
    op.drop_index("idx_agent_run_summaries_tenant", table_name="agent_run_summaries")
    op.drop_table("agent_run_summaries")
    op.drop_column("thread_summaries", "through_trigger_message_id")
