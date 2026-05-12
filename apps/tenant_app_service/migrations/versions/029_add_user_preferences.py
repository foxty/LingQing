"""Add users.preferences JSON column.

Revision ID: 029_add_user_preferences
Revises: 028_scheduled_task_ids_to_int
Create Date: 2026-03-31
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "029_add_user_preferences"
down_revision = "028_scheduled_task_ids_to_int"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "preferences",
            sa.JSON(),
            nullable=False,
            server_default="{}",
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "preferences")
