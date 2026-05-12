"""add rank to tag_values.

Revision ID: 018_add_rank_to_tag_values
Revises: 017_add_action_to_abac_policies
Create Date: 2026-02-28 18:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "018_add_rank_to_tag_values"
down_revision = "017_add_action_to_abac_policies"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tag_values", sa.Column("rank", sa.Integer(), nullable=True))
    op.create_index(
        "idx_tag_values_rank",
        "tag_values",
        ["tenant_id", "key_id", "rank"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_tag_values_rank", table_name="tag_values")
    op.drop_column("tag_values", "rank")
