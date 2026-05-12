"""Add dashboards table.

Revision ID: 004_add_dashboards
Revises: 003_add_task_runs
Create Date: 2026-01-18

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "004_add_dashboards"
down_revision = "003_add_task_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "dashboards",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "tenant_id",
            sa.Integer(),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("config", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column(
            "created_by",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "name", name="uq_dashboard_tenant_name"),
    )

    op.create_index("idx_dashboards_tenant", "dashboards", ["tenant_id"])
    op.create_index("idx_dashboards_created_by", "dashboards", ["created_by"])


def downgrade() -> None:
    op.drop_index("idx_dashboards_created_by", table_name="dashboards")
    op.drop_index("idx_dashboards_tenant", table_name="dashboards")
    op.drop_table("dashboards")
