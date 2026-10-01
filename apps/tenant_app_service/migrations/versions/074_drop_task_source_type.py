"""Drop deprecated source_type from scheduled_tasks and task_runs.

Revision ID: 074_drop_task_source_type
Revises: 073_document_source_sync
Create Date: 2026-10-01
"""

from alembic import op
import sqlalchemy as sa

revision = "074_drop_task_source_type"
down_revision = "073_document_source_sync"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("idx_scheduled_tasks_source_type", table_name="scheduled_tasks")
    op.drop_column("scheduled_tasks", "source_type")
    op.drop_column("task_runs", "source_type")


def downgrade() -> None:
    op.add_column(
        "task_runs",
        sa.Column("source_type", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "scheduled_tasks",
        sa.Column(
            "source_type",
            sa.String(length=20),
            nullable=False,
            server_default="agent",
        ),
    )
    op.create_index(
        "idx_scheduled_tasks_source_type",
        "scheduled_tasks",
        ["source_type"],
        unique=False,
    )
