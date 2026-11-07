"""Slack ingress dedupe by message identity (channel + ts).

Revision ID: 082_slack_msg_dedupe
Revises: 081_agent_run_summaries
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "082_slack_msg_dedupe"
down_revision = "081_agent_run_summaries"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Short-lived cache; safe to clear when changing the dedupe key shape.
    op.execute(sa.text("DELETE FROM slack_processed_events"))

    op.drop_constraint("uq_slack_processed_event", "slack_processed_events", type_="unique")
    op.alter_column(
        "slack_processed_events",
        "event_id",
        new_column_name="delivery_event_id",
        existing_type=sa.String(length=50),
        nullable=True,
        comment="Slack Events API envelope event_id (Ev…)",
    )
    op.alter_column(
        "slack_processed_events",
        "delivery_event_id",
        type_=sa.String(length=64),
        existing_nullable=True,
    )

    op.add_column(
        "slack_processed_events",
        sa.Column("slack_channel_id", sa.String(length=64), nullable=False, comment="Slack channel or DM id"),
    )
    op.add_column(
        "slack_processed_events",
        sa.Column("message_ts", sa.String(length=32), nullable=False, comment="Slack message ts"),
    )
    op.add_column(
        "slack_processed_events",
        sa.Column("thread_ts", sa.String(length=32), nullable=True, comment="Slack thread root ts when set"),
    )
    op.add_column(
        "slack_processed_events",
        sa.Column("inner_event_type", sa.String(length=32), nullable=True, comment="Inner event type"),
    )
    op.add_column(
        "slack_processed_events",
        sa.Column("slack_user_id", sa.String(length=64), nullable=True, comment="Slack user id (audit)"),
    )

    op.create_unique_constraint(
        "uq_slack_processed_message",
        "slack_processed_events",
        ["tenant_id", "slack_channel_id", "message_ts"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_slack_processed_message", "slack_processed_events", type_="unique")
    op.drop_column("slack_processed_events", "slack_user_id")
    op.drop_column("slack_processed_events", "inner_event_type")
    op.drop_column("slack_processed_events", "thread_ts")
    op.drop_column("slack_processed_events", "message_ts")
    op.drop_column("slack_processed_events", "slack_channel_id")

    op.alter_column(
        "slack_processed_events",
        "delivery_event_id",
        type_=sa.String(length=50),
        existing_nullable=True,
    )
    op.alter_column(
        "slack_processed_events",
        "delivery_event_id",
        new_column_name="event_id",
        existing_type=sa.String(length=50),
        nullable=False,
    )
    op.create_unique_constraint(
        "uq_slack_processed_event",
        "slack_processed_events",
        ["tenant_id", "event_id"],
    )
