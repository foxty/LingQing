"""Drop legacy created_by columns for API connector resources.

Revision ID: 042_api_owner_cols
Revises: 041_drop_legacy_owner_cols
Create Date: 2026-04-27
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "042_api_owner_cols"
down_revision = "041_drop_legacy_owner_cols"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("api_operation_index", "created_by")
    op.drop_column("api_connectors", "created_by")


def downgrade() -> None:
    op.add_column("api_connectors", sa.Column("created_by", sa.Integer(), nullable=True))
    op.create_foreign_key(None, "api_connectors", "users", ["created_by"], ["id"], ondelete="SET NULL")
    op.execute("UPDATE api_connectors SET created_by = owner_id WHERE created_by IS NULL AND owner_id IS NOT NULL")

    op.add_column("api_operation_index", sa.Column("created_by", sa.Integer(), nullable=True))
    op.create_foreign_key(None, "api_operation_index", "users", ["created_by"], ["id"], ondelete="SET NULL")
    op.execute("UPDATE api_operation_index SET created_by = owner_id WHERE created_by IS NULL AND owner_id IS NOT NULL")
