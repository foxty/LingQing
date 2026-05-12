"""Add persisted reports table for durable report artifacts.

Revision ID: 024_add_reports
Revises: 023_fix_datetime_tz
Create Date: 2026-03-25

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "024_add_reports"
down_revision = "023_fix_datetime_tz"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create reports table and related indexes."""
    op.create_table(
        "reports",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column(
            "source_thread_id",
            sa.String(length=255),
            nullable=True,
            comment="Original thread ID where the report was generated (no FK by design)",
        ),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("format", sa.String(length=20), nullable=False, server_default="markdown"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
        sa.Column("report_metadata", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("is_shared", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("share_token", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("share_token", name="uq_reports_share_token"),
    )

    op.create_index("idx_reports_tenant", "reports", ["tenant_id"], unique=False)
    op.create_index("idx_reports_created_by", "reports", ["created_by"], unique=False)
    op.create_index("idx_reports_tenant_created", "reports", ["tenant_id", "created_at"], unique=False)
    op.create_index(
        "idx_reports_user_created",
        "reports",
        ["tenant_id", "created_by", "created_at"],
        unique=False,
    )
    op.create_index("idx_reports_share_token", "reports", ["share_token"], unique=False)


def downgrade() -> None:
    """Drop reports table and indexes."""
    op.drop_index("idx_reports_share_token", table_name="reports")
    op.drop_index("idx_reports_user_created", table_name="reports")
    op.drop_index("idx_reports_tenant_created", table_name="reports")
    op.drop_index("idx_reports_created_by", table_name="reports")
    op.drop_index("idx_reports_tenant", table_name="reports")
    op.drop_table("reports")
