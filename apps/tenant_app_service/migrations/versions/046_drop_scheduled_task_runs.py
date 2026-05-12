"""Drop scheduled_task_runs table (superseded by task_runs).

All execution history for ScheduledTask is now written to task_runs
via the unified TaskRun model. The scheduled_task_runs table is no
longer written to and can be safely removed.

Revision ID: 046_drop_scheduled_task_runs
Revises: 045_unified_task_model
Create Date: 2026-05-02
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "046_drop_scheduled_task_runs"
down_revision = "045_unified_task_model"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("idx_scheduled_task_runs_task_started", table_name="scheduled_task_runs")
    op.drop_index("idx_scheduled_task_runs_status", table_name="scheduled_task_runs")
    op.drop_table("scheduled_task_runs")


def downgrade() -> None:
    op.create_table(
        "scheduled_task_runs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("scheduled_task_id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("result", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["scheduled_task_id"], ["scheduled_tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_scheduled_task_runs_task_started", "scheduled_task_runs", ["scheduled_task_id", "started_at"])
    op.create_index("idx_scheduled_task_runs_status", "scheduled_task_runs", ["status"])
