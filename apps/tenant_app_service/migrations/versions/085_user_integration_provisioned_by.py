"""Add provisioned_by audit fields on user_integration_credentials.

Revision ID: 085_byot_provisioned_by
Revises: 084_audit_events_columns_indexes
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "085_byot_provisioned_by"
down_revision = "084_audit_events_columns_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user_integration_credentials",
        sa.Column("provisioned_by_user_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "user_integration_credentials",
        sa.Column("provisioned_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_user_integration_cred_provisioned_by",
        "user_integration_credentials",
        "users",
        ["provisioned_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_user_integration_cred_provisioned_by",
        "user_integration_credentials",
        type_="foreignkey",
    )
    op.drop_column("user_integration_credentials", "provisioned_at")
    op.drop_column("user_integration_credentials", "provisioned_by_user_id")