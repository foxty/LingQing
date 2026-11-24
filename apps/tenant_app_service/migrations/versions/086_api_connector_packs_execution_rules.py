"""Add API connector pack identity and execution rules.

Revision ID: 086_api_connector_pack_rules
Revises: 085_byot_provisioned_by
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "086_api_connector_pack_rules"
down_revision = "085_byot_provisioned_by"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("api_connectors", sa.Column("pack_ref", sa.String(length=160), nullable=True))
    op.add_column(
        "api_connectors",
        sa.Column("execution_rules", sa.JSON(), nullable=False, server_default="{}"),
    )
    op.create_unique_constraint(
        "uq_api_connectors_tenant_pack_ref",
        "api_connectors",
        ["tenant_id", "pack_ref"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_api_connectors_tenant_pack_ref", "api_connectors", type_="unique")
    op.drop_column("api_connectors", "execution_rules")
    op.drop_column("api_connectors", "pack_ref")
