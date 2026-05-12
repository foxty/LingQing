"""Add artifact_shares table for explicit user-to-user artifact sharing.

Revision ID: 031_add_artifact_shares
Revises: 030_add_live_apps
Create Date: 2026-04-12
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "031_add_artifact_shares"
down_revision = "030_add_live_apps"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "artifact_shares",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("artifact_id", sa.Integer(), nullable=False),
        sa.Column("shared_with_user_id", sa.Integer(), nullable=False),
        sa.Column("permission", sa.String(length=10), nullable=False, server_default="read"),
        sa.Column("shared_by", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["artifact_id"], ["artifacts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["shared_with_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["shared_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("artifact_id", "shared_with_user_id", name="uq_artifact_share"),
    )
    op.create_index("idx_artifact_shares_user", "artifact_shares", ["shared_with_user_id"])
    op.create_index("idx_artifact_shares_artifact", "artifact_shares", ["artifact_id"])


def downgrade() -> None:
    op.drop_index("idx_artifact_shares_artifact", table_name="artifact_shares")
    op.drop_index("idx_artifact_shares_user", table_name="artifact_shares")
    op.drop_table("artifact_shares")
