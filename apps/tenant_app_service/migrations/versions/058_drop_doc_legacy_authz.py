"""Remove legacy document-level ABAC policies and tag bindings.

Revision ID: 058_drop_doc_legacy_authz
Revises: 057_doc_index_parent_id
Create Date: 2026-08-31

Document access is collection-scoped; document-level ABAC and tags are obsolete.
"""

import sqlalchemy as sa
from alembic import op

revision = "058_drop_doc_legacy_authz"
down_revision = "057_doc_index_parent_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("DELETE FROM tag_bindings WHERE resource_type = 'document'"))
    op.execute(sa.text("DELETE FROM resource_tag_configs WHERE resource_type = 'document'"))
    op.execute(sa.text("DELETE FROM abac_policies WHERE resource_type = 'document'"))


def downgrade() -> None:
    pass
