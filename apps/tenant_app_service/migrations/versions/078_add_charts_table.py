"""Add charts table for artifact-backed chart resources.

Revision ID: 078_add_charts_table
Revises: 077_llm_profile_runtime_config
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "078_add_charts_table"
down_revision = "077_llm_profile_runtime_config"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "charts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("thread_id", sa.String(length=255), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False, server_default=""),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_charts_tenant", "charts", ["tenant_id"], unique=False)
    op.create_index("idx_charts_tenant_thread", "charts", ["tenant_id", "thread_id"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_charts_tenant_thread", table_name="charts")
    op.drop_index("idx_charts_tenant", table_name="charts")
    op.drop_table("charts")
