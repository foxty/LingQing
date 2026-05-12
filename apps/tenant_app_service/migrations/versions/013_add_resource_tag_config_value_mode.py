"""add value_mode to resource_tag_configs.

Revision ID: 013_rtc_value_mode
Revises: 012_add_tag_key_color
Create Date: 2026-02-10 13:05:00.000000
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "013_rtc_value_mode"
down_revision = "012_add_tag_key_color"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "resource_tag_configs",
        sa.Column("value_mode", sa.String(length=20), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("resource_tag_configs", "value_mode")
