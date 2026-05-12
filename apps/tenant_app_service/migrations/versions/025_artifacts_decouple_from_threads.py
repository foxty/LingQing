"""Decouple artifacts from thread lifecycle.

Revision ID: 025_artifacts_decouple
Revises: 024_add_reports
Create Date: 2026-03-27

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "025_artifacts_decouple"
down_revision = "024_add_reports"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Make thread linkage optional and remove cascade FK to chat_threads."""
    # Drop FK if present so artifact rows survive thread deletion.
    # PostgreSQL default FK name is typically <table>_<column>_fkey.
    with op.batch_alter_table("thread_artifacts") as batch_op:
        try:
            batch_op.drop_constraint("thread_artifacts_thread_id_fkey", type_="foreignkey")
        except Exception:
            # Keep migration resilient across environments where FK name differs
            # or where the constraint was already removed.
            pass

    op.alter_column(
        "thread_artifacts",
        "thread_id",
        existing_type=sa.String(length=255),
        nullable=True,
    )


def downgrade() -> None:
    """Restore required thread linkage with cascading delete behavior."""
    op.alter_column(
        "thread_artifacts",
        "thread_id",
        existing_type=sa.String(length=255),
        nullable=False,
    )
    with op.batch_alter_table("thread_artifacts") as batch_op:
        batch_op.create_foreign_key(
            "thread_artifacts_thread_id_fkey",
            "chat_threads",
            ["thread_id"],
            ["id"],
            ondelete="CASCADE",
        )
