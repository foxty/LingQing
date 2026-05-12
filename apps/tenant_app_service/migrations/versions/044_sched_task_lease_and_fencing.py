"""Add lease ownership and fencing fields for scheduled tasks.

Revision ID: 044_sched_task_lease_fencing
Revises: 043_owner_not_null
Create Date: 2026-04-30
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "044_sched_task_lease_fencing"
down_revision = "043_owner_not_null"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("scheduled_tasks", sa.Column("owner_instance_id", sa.String(length=128), nullable=True))
    op.add_column("scheduled_tasks", sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("scheduled_tasks", sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "scheduled_tasks",
        sa.Column("fencing_token", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index(
        "idx_scheduled_tasks_status_lease_expires",
        "scheduled_tasks",
        ["status", "lease_expires_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_scheduled_tasks_status_lease_expires", table_name="scheduled_tasks")
    op.drop_column("scheduled_tasks", "fencing_token")
    op.drop_column("scheduled_tasks", "lease_expires_at")
    op.drop_column("scheduled_tasks", "heartbeat_at")
    op.drop_column("scheduled_tasks", "owner_instance_id")
