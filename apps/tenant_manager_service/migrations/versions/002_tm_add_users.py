"""add tenant manager local users.

Revision ID: 002_tm_add_users
Revises: 001_tm_initial_schema
Create Date: 2026-03-09 10:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "002_tm_add_users"
down_revision = "001_tm_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tenant_manager_users",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("username", sa.String(length=100), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=50), nullable=False, server_default="platform_ops"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")
        ),
        sa.UniqueConstraint("username", name="uq_tm_users_username"),
    )
    op.create_index("idx_tm_users_username", "tenant_manager_users", ["username"], unique=False)
    op.create_index("idx_tm_users_status_updated", "tenant_manager_users", ["status", "updated_at"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_tm_users_status_updated", table_name="tenant_manager_users")
    op.drop_index("idx_tm_users_username", table_name="tenant_manager_users")
    op.drop_table("tenant_manager_users")
