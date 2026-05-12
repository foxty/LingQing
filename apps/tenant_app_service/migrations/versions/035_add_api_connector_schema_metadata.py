"""Add schema_metadata to api_connectors.

Revision ID: 035_api_connector_meta
Revises: 034_api_op_source_sync
Create Date: 2026-04-22
"""

import sqlalchemy as sa
from alembic import op

revision = "035_api_connector_meta"
down_revision = "034_api_op_source_sync"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "api_connectors",
        sa.Column("schema_metadata", sa.JSON(), nullable=False, server_default="{}"),
    )


def downgrade() -> None:
    op.drop_column("api_connectors", "schema_metadata")
