"""Remove public share columns from reports (use artifact_shares for ACL).

Revision ID: 032_remove_report_public_share
Revises: 031_add_artifact_shares
Create Date: 2026-04-13
"""

import sqlalchemy as sa
from alembic import op

revision = "032_remove_report_public_share"
down_revision = "031_add_artifact_shares"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("idx_reports_share_token", table_name="reports")
    op.drop_constraint("uq_reports_share_token", "reports", type_="unique")
    op.drop_column("reports", "is_shared")
    op.drop_column("reports", "share_token")


def downgrade() -> None:
    op.add_column(
        "reports",
        sa.Column("is_shared", sa.Boolean(), nullable=False, server_default="0"),
    )
    op.add_column("reports", sa.Column("share_token", sa.String(length=64), nullable=True))
    op.create_unique_constraint("uq_reports_share_token", "reports", ["share_token"])
    op.create_index("idx_reports_share_token", "reports", ["share_token"], unique=False)
