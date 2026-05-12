"""Drop unused acl_grants inherit_from columns.

Those columns were added for copying KB/DS/API ACL rows onto an agent share.
Delegation now evaluates the agent's attached IDs at chat time instead.

Revision ID: 068_drop_acl_grant_inherit
Revises: 067_drop_share_assigned
"""

import sqlalchemy as sa
from alembic import op

revision = "068_drop_acl_grant_inherit"
down_revision = "067_drop_share_assigned"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("idx_acl_grants_inherit", table_name="acl_grants")
    op.drop_column("acl_grants", "inherit_from_id")
    op.drop_column("acl_grants", "inherit_from_type")


def downgrade() -> None:
    op.add_column("acl_grants", sa.Column("inherit_from_type", sa.String(length=50), nullable=True))
    op.add_column("acl_grants", sa.Column("inherit_from_id", sa.Integer(), nullable=True))
    op.create_index(
        "idx_acl_grants_inherit",
        "acl_grants",
        ["tenant_id", "inherit_from_type", "inherit_from_id"],
    )
