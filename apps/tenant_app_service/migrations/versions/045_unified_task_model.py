"""Unify task model: extend ScheduledTask + TaskRun for unified observability.

Revision ID: 045_unified_task_model
Revises: 044_sched_task_lease_fencing
Create Date: 2026-05-01
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "045_unified_task_model"
down_revision = "044_sched_task_lease_fencing"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -----------------------------------------------------------------------
    # scheduled_tasks: add unified-task fields
    # -----------------------------------------------------------------------
    op.add_column(
        "scheduled_tasks",
        sa.Column("stable_key", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "scheduled_tasks",
        sa.Column("source_type", sa.String(length=20), nullable=False, server_default="agent"),
    )
    op.add_column(
        "scheduled_tasks",
        sa.Column("execution_mode", sa.String(length=20), nullable=False, server_default="internal"),
    )
    op.add_column(
        "scheduled_tasks",
        sa.Column("handler_ref", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "scheduled_tasks",
        sa.Column("input_params", sa.JSON(), nullable=True),
    )

    # Unique constraint: one stable_key per tenant
    op.create_unique_constraint(
        "uq_scheduled_tasks_tenant_stable_key",
        "scheduled_tasks",
        ["tenant_id", "stable_key"],
    )
    # Indexes for observability queries
    op.create_index(
        "idx_scheduled_tasks_source_type",
        "scheduled_tasks",
        ["source_type"],
        unique=False,
    )
    op.create_index(
        "idx_scheduled_tasks_tenant_stable_key",
        "scheduled_tasks",
        ["tenant_id", "stable_key"],
        unique=False,
    )

    # -----------------------------------------------------------------------
    # task_runs: add FK + observability fields
    # -----------------------------------------------------------------------
    op.add_column(
        "task_runs",
        sa.Column(
            "scheduled_task_id",
            sa.Integer(),
            sa.ForeignKey("scheduled_tasks.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "task_runs",
        sa.Column(
            "tenant_id",
            sa.Integer(),
            sa.ForeignKey("tenants.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "task_runs",
        sa.Column("source_type", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "task_runs",
        sa.Column("orchestration_run_id", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "task_runs",
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="1"),
    )

    # Indexes for TaskRun observability queries
    op.create_index(
        "idx_task_runs_scheduled_task",
        "task_runs",
        ["scheduled_task_id"],
        unique=False,
    )
    op.create_index(
        "idx_task_runs_orchestration_run",
        "task_runs",
        ["orchestration_run_id"],
        unique=False,
    )
    op.create_index(
        "idx_task_runs_tenant_started",
        "task_runs",
        ["tenant_id", "started_at"],
        unique=False,
    )


def downgrade() -> None:
    # task_runs
    op.drop_index("idx_task_runs_tenant_started", table_name="task_runs")
    op.drop_index("idx_task_runs_orchestration_run", table_name="task_runs")
    op.drop_index("idx_task_runs_scheduled_task", table_name="task_runs")
    op.drop_column("task_runs", "attempt")
    op.drop_column("task_runs", "orchestration_run_id")
    op.drop_column("task_runs", "source_type")
    op.drop_column("task_runs", "tenant_id")
    op.drop_column("task_runs", "scheduled_task_id")

    # scheduled_tasks
    op.drop_index("idx_scheduled_tasks_tenant_stable_key", table_name="scheduled_tasks")
    op.drop_index("idx_scheduled_tasks_source_type", table_name="scheduled_tasks")
    op.drop_constraint("uq_scheduled_tasks_tenant_stable_key", "scheduled_tasks", type_="unique")
    op.drop_column("scheduled_tasks", "input_params")
    op.drop_column("scheduled_tasks", "handler_ref")
    op.drop_column("scheduled_tasks", "execution_mode")
    op.drop_column("scheduled_tasks", "source_type")
    op.drop_column("scheduled_tasks", "stable_key")
