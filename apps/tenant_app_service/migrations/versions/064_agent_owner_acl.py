"""Add agent owner_id and linked ACL grant inheritance.

Revision ID: 064_agent_owner_acl
Revises: 063_widen_task_run_name
"""

import sqlalchemy as sa
from alembic import op

revision = "064_agent_owner_acl"
down_revision = "063_widen_task_run_name"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("agents", sa.Column("owner_id", sa.Integer(), nullable=False))
    op.create_index("ix_agents_owner_id", "agents", ["owner_id"])
    op.create_foreign_key("fk_agents_owner_id_users", "agents", "users", ["owner_id"], ["id"], ondelete="CASCADE")

    op.add_column("acl_grants", sa.Column("inherit_from_type", sa.String(length=50), nullable=True))
    op.add_column("acl_grants", sa.Column("inherit_from_id", sa.Integer(), nullable=True))
    op.create_index(
        "idx_acl_grants_inherit",
        "acl_grants",
        ["tenant_id", "inherit_from_type", "inherit_from_id"],
    )


def downgrade() -> None:
    op.drop_index("idx_acl_grants_inherit", table_name="acl_grants")
    op.drop_column("acl_grants", "inherit_from_id")
    op.drop_column("acl_grants", "inherit_from_type")
    op.drop_constraint("fk_agents_owner_id_users", "agents", type_="foreignkey")
    op.drop_index("ix_agents_owner_id", table_name="agents")
    op.drop_column("agents", "owner_id")
