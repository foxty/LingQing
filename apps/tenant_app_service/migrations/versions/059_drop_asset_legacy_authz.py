"""Remove legacy asset-level ABAC/ACL/tag data and backfill asset index parent_id.

Revision ID: 059_drop_asset_legacy_authz
Revises: 058_drop_doc_legacy_authz
Create Date: 2026-09-01

Asset access is data-source-scoped; asset-level ABAC, ACL, and tags are obsolete.
"""

import sqlalchemy as sa
from alembic import op

revision = "059_drop_asset_legacy_authz"
down_revision = "058_drop_doc_legacy_authz"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("DELETE FROM acl_grants WHERE resource_type IN ('asset', 'asset_metadata')"))
    op.execute(sa.text("DELETE FROM resource_acl WHERE resource_type IN ('asset', 'asset_metadata')"))
    op.execute(sa.text("DELETE FROM tag_bindings WHERE resource_type IN ('asset', 'asset_metadata')"))
    op.execute(sa.text("DELETE FROM resource_tag_configs WHERE resource_type IN ('asset', 'asset_metadata')"))
    op.execute(sa.text("DELETE FROM abac_policies WHERE resource_type IN ('asset', 'asset_metadata')"))
    op.execute(
        sa.text(
            """
            UPDATE resource_index ri
            SET parent_id = am.data_source_id
            FROM asset_metadata am
            WHERE ri.resource_type = 'asset'
              AND ri.resource_id = am.id
              AND ri.parent_id IS NULL
            """
        )
    )


def downgrade() -> None:
    pass
