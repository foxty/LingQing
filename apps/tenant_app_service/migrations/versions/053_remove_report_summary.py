"""Remove summary field from reports table.

Revision ID: 053_remove_report_summary
Revises: 052_document_owner_dedup
Create Date: 2026-05-16

Changes:
- Drop summary column from reports table (redundant with content field)
"""

import sqlalchemy as sa
from alembic import op

revision = "053_remove_report_summary"
down_revision = "052_document_owner_dedup"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_column("reports", "summary")


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column("reports", sa.Column("summary", sa.Text(), nullable=True))
