"""drop deprecated tag_keys.value_mode.

Revision ID: 015_drop_tag_key_value_mode
Revises: 014_rtc_value_mode_nn
Create Date: 2026-02-23 10:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "015_drop_tag_key_value_mode"
down_revision = "014_rtc_value_mode_nn"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("tag_keys", "value_mode")


def downgrade() -> None:
    op.add_column(
        "tag_keys",
        sa.Column("value_mode", sa.String(length=20), nullable=False, server_default="inclusive"),
    )
    op.alter_column("tag_keys", "value_mode", server_default=None)
