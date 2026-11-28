"""Track installed semver for API connector integration packs.

Revision ID: 088_api_connector_pack_ver
Revises: 087_api_connector_agent_help
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "088_api_connector_pack_ver"
down_revision = "087_api_connector_agent_help"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "api_connectors",
        sa.Column(
            "installed_pack_version",
            sa.String(length=32),
            nullable=True,
            comment="Semver of the integration pack manifest last applied to this connector",
        ),
    )


def downgrade() -> None:
    op.drop_column("api_connectors", "installed_pack_version")