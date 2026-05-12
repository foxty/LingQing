"""Convert scheduled task IDs from UUID string to integer.

Revision ID: 028_scheduled_task_ids_to_int
Revises: 027_sched_tasks_notifications
Create Date: 2026-03-30
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "028_scheduled_task_ids_to_int"
down_revision = "027_sched_tasks_notifications"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SEQUENCE IF NOT EXISTS scheduled_tasks_id_seq")

    op.add_column("scheduled_tasks", sa.Column("id_int", sa.Integer(), nullable=True))
    op.execute("ALTER TABLE scheduled_tasks ALTER COLUMN id_int SET DEFAULT nextval('scheduled_tasks_id_seq')")
    op.execute("UPDATE scheduled_tasks SET id_int = nextval('scheduled_tasks_id_seq') WHERE id_int IS NULL")
    op.execute(
        "SELECT setval('scheduled_tasks_id_seq', COALESCE((SELECT MAX(id_int) FROM scheduled_tasks), 1), true)"
    )

    op.add_column("scheduled_task_runs", sa.Column("scheduled_task_id_int", sa.Integer(), nullable=True))
    op.execute(
        """
        UPDATE scheduled_task_runs r
        SET scheduled_task_id_int = t.id_int
        FROM scheduled_tasks t
        WHERE r.scheduled_task_id = t.id
        """
    )

    op.drop_index("idx_scheduled_task_runs_task_started", table_name="scheduled_task_runs")
    op.execute("ALTER TABLE scheduled_task_runs DROP CONSTRAINT IF EXISTS scheduled_task_runs_scheduled_task_id_fkey")

    op.execute("ALTER TABLE scheduled_tasks DROP CONSTRAINT IF EXISTS scheduled_tasks_pkey")
    op.drop_column("scheduled_tasks", "id")
    op.alter_column("scheduled_tasks", "id_int", new_column_name="id")
    op.alter_column("scheduled_tasks", "id", nullable=False)
    op.execute("ALTER TABLE scheduled_tasks ADD PRIMARY KEY (id)")

    op.drop_column("scheduled_task_runs", "scheduled_task_id")
    op.alter_column("scheduled_task_runs", "scheduled_task_id_int", new_column_name="scheduled_task_id")
    op.alter_column("scheduled_task_runs", "scheduled_task_id", nullable=False)
    op.create_foreign_key(
        "scheduled_task_runs_scheduled_task_id_fkey",
        "scheduled_task_runs",
        "scheduled_tasks",
        ["scheduled_task_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "idx_scheduled_task_runs_task_started",
        "scheduled_task_runs",
        ["scheduled_task_id", "started_at"],
        unique=False,
    )


def downgrade() -> None:
    op.add_column("scheduled_tasks", sa.Column("id_str", sa.String(length=36), nullable=True))
    op.execute("UPDATE scheduled_tasks SET id_str = id::text")

    op.add_column("scheduled_task_runs", sa.Column("scheduled_task_id_str", sa.String(length=36), nullable=True))
    op.execute(
        """
        UPDATE scheduled_task_runs r
        SET scheduled_task_id_str = t.id_str
        FROM scheduled_tasks t
        WHERE r.scheduled_task_id = t.id
        """
    )

    op.drop_index("idx_scheduled_task_runs_task_started", table_name="scheduled_task_runs")
    op.drop_constraint("scheduled_task_runs_scheduled_task_id_fkey", "scheduled_task_runs", type_="foreignkey")

    op.execute("ALTER TABLE scheduled_tasks DROP CONSTRAINT IF EXISTS scheduled_tasks_pkey")
    op.drop_column("scheduled_tasks", "id")
    op.alter_column("scheduled_tasks", "id_str", new_column_name="id")
    op.alter_column("scheduled_tasks", "id", nullable=False)
    op.execute("ALTER TABLE scheduled_tasks ADD PRIMARY KEY (id)")

    op.drop_column("scheduled_task_runs", "scheduled_task_id")
    op.alter_column("scheduled_task_runs", "scheduled_task_id_str", new_column_name="scheduled_task_id")
    op.alter_column("scheduled_task_runs", "scheduled_task_id", nullable=False)
    op.create_foreign_key(
        "scheduled_task_runs_scheduled_task_id_fkey",
        "scheduled_task_runs",
        "scheduled_tasks",
        ["scheduled_task_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "idx_scheduled_task_runs_task_started",
        "scheduled_task_runs",
        ["scheduled_task_id", "started_at"],
        unique=False,
    )
