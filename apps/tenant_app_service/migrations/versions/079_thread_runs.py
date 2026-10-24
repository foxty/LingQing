"""Thread main messages, agent runs, and run-scoped messages.

Revision ID: 079_thread_runs
Revises: 078_add_charts_table
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "079_thread_runs"
down_revision = "078_add_charts_table"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "thread_main_messages",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("message_id", sa.String(length=255), nullable=False),
        sa.Column("thread_id", sa.String(length=255), nullable=False),
        sa.Column("type", sa.String(length=16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("agent_id", sa.Integer(), nullable=True),
        sa.Column("trigger_message_id", sa.String(length=255), nullable=True),
        sa.Column("agent_run_id", sa.String(length=36), nullable=True),
        sa.Column("invoke_index", sa.Integer(), nullable=True),
        sa.Column("session_id", sa.String(length=255), nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("additional_kwargs", sa.JSON(), nullable=True),
        sa.Column("message_metadata", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["thread_id"], ["chat_threads.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("message_id", name="uq_thread_main_messages_message_id"),
        sa.UniqueConstraint("agent_run_id", name="uq_thread_main_messages_agent_run_id"),
    )
    op.create_index(
        "idx_thread_main_messages_thread_created_id",
        "thread_main_messages",
        ["thread_id", "created_at", "id"],
    )
    op.create_index(
        "idx_thread_main_messages_trigger",
        "thread_main_messages",
        ["thread_id", "trigger_message_id"],
    )

    op.create_table(
        "agent_runs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("thread_id", sa.String(length=255), nullable=False),
        sa.Column("agent_id", sa.Integer(), nullable=False),
        sa.Column("trigger_message_id", sa.String(length=255), nullable=False),
        sa.Column("invoke_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="queued"),
        sa.Column("session_id", sa.String(length=255), nullable=False),
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
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["thread_id"], ["chat_threads.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("trigger_message_id", "invoke_index", name="uq_agent_runs_trigger_invoke"),
    )
    op.create_index("idx_agent_runs_tenant", "agent_runs", ["tenant_id"])
    op.create_index("idx_agent_runs_thread_status", "agent_runs", ["thread_id", "status"])
    op.create_index("idx_agent_runs_trigger", "agent_runs", ["thread_id", "trigger_message_id"])

    op.create_table(
        "agent_run_messages",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("message_id", sa.String(length=255), nullable=True),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("thread_id", sa.String(length=255), nullable=False),
        sa.Column("type", sa.String(length=50), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("is_summarized", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("tool_calls", sa.JSON(), nullable=True),
        sa.Column("additional_kwargs", sa.JSON(), nullable=True),
        sa.Column("session_id", sa.String(length=255), nullable=True),
        sa.Column("agent_id", sa.Integer(), nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("message_metadata", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["run_id"], ["agent_runs.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "idx_agent_run_messages_run_created_id",
        "agent_run_messages",
        ["run_id", "created_at", "id"],
    )
    op.create_index("idx_agent_run_messages_session", "agent_run_messages", ["session_id"])
    op.create_index("idx_agent_run_messages_message_id", "agent_run_messages", ["message_id"])


def downgrade() -> None:
    op.drop_table("agent_run_messages")
    op.drop_table("agent_runs")
    op.drop_table("thread_main_messages")
