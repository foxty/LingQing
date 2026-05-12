"""drop deprecated tag_keys.type.

Revision ID: 016_drop_tag_key_type
Revises: 015_drop_tag_key_value_mode
Create Date: 2026-02-23 11:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "016_drop_tag_key_type"
down_revision = "015_drop_tag_key_value_mode"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("tag_keys", "type")


def downgrade() -> None:
    op.add_column(
        "tag_keys",
        sa.Column("type", sa.String(length=20), nullable=False, server_default="enum"),
    )
    op.alter_column("tag_keys", "type", server_default=None)
