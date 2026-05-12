"""add tag key color.

Revision ID: 012_add_tag_key_color
Revises: 011_tag_system_and_abac
Create Date: 2026-02-10 12:40:00.000000
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "012_add_tag_key_color"
down_revision = "011_tag_system_and_abac"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tag_keys", sa.Column("color", sa.String(length=20), nullable=True))
    op.drop_column("tag_keys", "allowed_values")


def downgrade() -> None:
    op.add_column("tag_keys", sa.Column("allowed_values", sa.JSON(), nullable=True))
    op.drop_column("tag_keys", "color")
