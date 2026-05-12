"""Add unified scheduled tasks and notification tables.

Revision ID: 027_unified_scheduled_tasks_notifications
Revises: 026_split_artifacts_links
Create Date: 2026-03-30
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "027_sched_tasks_notifications"
down_revision = "026_split_artifacts_links"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create scheduled task and notification tables."""
    op.create_table(
        "scheduled_tasks",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("task_type", sa.String(length=50), nullable=False),
        sa.Column("task_config", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("schedule_type", sa.String(length=20), nullable=False),
        sa.Column("schedule_spec", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notification_channels", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
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
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_scheduled_tasks_status_next_run",
        "scheduled_tasks",
        ["status", "next_run_at"],
        unique=False,
    )
    op.create_index(
        "idx_scheduled_tasks_tenant_user",
        "scheduled_tasks",
        ["tenant_id", "user_id"],
        unique=False,
    )
    op.create_index("idx_scheduled_tasks_type", "scheduled_tasks", ["task_type"], unique=False)

    op.create_table(
        "scheduled_task_runs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("scheduled_task_id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("result", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["scheduled_task_id"], ["scheduled_tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_scheduled_task_runs_task_started",
        "scheduled_task_runs",
        ["scheduled_task_id", "started_at"],
        unique=False,
    )
    op.create_index("idx_scheduled_task_runs_status", "scheduled_task_runs", ["status"], unique=False)

    op.create_table(
        "notifications",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("is_read", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_notifications_user_created",
        "notifications",
        ["tenant_id", "user_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "idx_notifications_user_read",
        "notifications",
        ["tenant_id", "user_id", "is_read"],
        unique=False,
    )

    op.create_table(
        "notification_channel_configs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("channel_type", sa.String(length=50), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
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
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "channel_type", name="uq_notification_channel_tenant_type"),
    )
    op.create_index(
        "idx_notification_channel_tenant_enabled",
        "notification_channel_configs",
        ["tenant_id", "is_enabled"],
        unique=False,
    )

    op.create_table(
        "user_notification_preferences",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("channels", sa.JSON(), nullable=False, server_default="[]"),
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
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "user_id", "event_type", name="uq_user_notification_pref"),
    )
    op.create_index(
        "idx_user_notification_pref_user",
        "user_notification_preferences",
        ["tenant_id", "user_id"],
        unique=False,
    )


def downgrade() -> None:
    """Drop scheduled task and notification tables."""
    op.drop_index("idx_user_notification_pref_user", table_name="user_notification_preferences")
    op.drop_table("user_notification_preferences")

    op.drop_index("idx_notification_channel_tenant_enabled", table_name="notification_channel_configs")
    op.drop_table("notification_channel_configs")

    op.drop_index("idx_notifications_user_read", table_name="notifications")
    op.drop_index("idx_notifications_user_created", table_name="notifications")
    op.drop_table("notifications")

    op.drop_index("idx_scheduled_task_runs_status", table_name="scheduled_task_runs")
    op.drop_index("idx_scheduled_task_runs_task_started", table_name="scheduled_task_runs")
    op.drop_table("scheduled_task_runs")

    op.drop_index("idx_scheduled_tasks_type", table_name="scheduled_tasks")
    op.drop_index("idx_scheduled_tasks_tenant_user", table_name="scheduled_tasks")
    op.drop_index("idx_scheduled_tasks_status_next_run", table_name="scheduled_tasks")
    op.drop_table("scheduled_tasks")
