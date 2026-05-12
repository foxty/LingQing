"""make resource_tag_configs.value_mode not null.

Revision ID: 014_rtc_value_mode_nn
Revises: 013_rtc_value_mode
Create Date: 2026-02-10 13:20:00.000000
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "014_rtc_value_mode_nn"
down_revision = "013_rtc_value_mode"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE resource_tag_configs rtc
        SET value_mode = tk.value_mode
        FROM tag_keys tk
        WHERE rtc.tag_key_id = tk.id
          AND rtc.value_mode IS NULL
        """
    )
    op.alter_column(
        "resource_tag_configs",
        "value_mode",
        existing_type=sa.String(length=20),
        nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "resource_tag_configs",
        "value_mode",
        existing_type=sa.String(length=20),
        nullable=True,
    )
