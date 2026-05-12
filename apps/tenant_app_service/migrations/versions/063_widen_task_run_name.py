"""Align scheduled task name columns to 120-char limit.

Revision ID: 063_widen_task_run_name
Revises: 062_doc_storage_fts
"""

import sqlalchemy as sa
from alembic import op

revision = "063_widen_task_run_name"
down_revision = "062_doc_storage_fts"
branch_labels = None
depends_on = None

_TASK_NAME_MAX_LENGTH = 120


def upgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE scheduled_tasks SET name = LEFT(name, :max_len) WHERE LENGTH(name) > :max_len"
        ).bindparams(max_len=_TASK_NAME_MAX_LENGTH)
    )
    op.execute(
        sa.text(
            "UPDATE task_runs SET task_name = LEFT(task_name, :max_len) WHERE LENGTH(task_name) > :max_len"
        ).bindparams(max_len=_TASK_NAME_MAX_LENGTH)
    )
    op.alter_column(
        "scheduled_tasks",
        "name",
        existing_type=sa.String(length=255),
        type_=sa.String(length=_TASK_NAME_MAX_LENGTH),
        existing_nullable=False,
    )
    op.alter_column(
        "task_runs",
        "task_name",
        existing_type=sa.String(length=100),
        type_=sa.String(length=_TASK_NAME_MAX_LENGTH),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "task_runs",
        "task_name",
        existing_type=sa.String(length=_TASK_NAME_MAX_LENGTH),
        type_=sa.String(length=100),
        existing_nullable=False,
    )
    op.alter_column(
        "scheduled_tasks",
        "name",
        existing_type=sa.String(length=_TASK_NAME_MAX_LENGTH),
        type_=sa.String(length=255),
        existing_nullable=False,
    )
