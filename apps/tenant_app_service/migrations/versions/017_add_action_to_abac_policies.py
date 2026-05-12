"""add action to abac_policies.

Revision ID: 017_add_action_to_abac_policies
Revises: 016_drop_tag_key_type
Create Date: 2026-02-27 10:30:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "017_add_action_to_abac_policies"
down_revision = "016_drop_tag_key_type"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "abac_policies",
        sa.Column("action", sa.String(length=20), nullable=False, server_default="read"),
    )
    op.create_index(
        "idx_abac_policies_resource_action",
        "abac_policies",
        ["tenant_id", "resource_type", "action", "status"],
        unique=False,
    )
    op.alter_column("abac_policies", "action", server_default=None)


def downgrade() -> None:
    op.drop_index("idx_abac_policies_resource_action", table_name="abac_policies")
    op.drop_column("abac_policies", "action")
