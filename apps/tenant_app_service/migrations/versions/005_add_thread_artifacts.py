"""Add thread_artifacts table.

Revision ID: 005_add_thread_artifacts
Revises: 004_add_dashboards
Create Date: 2026-01-19 10:00:00.000000

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = "005_add_thread_artifacts"
down_revision = "004_add_dashboards"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create thread_artifacts table for tracking artifacts created in chat threads."""
    op.create_table(
        "thread_artifacts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("thread_id", sa.String(length=255), nullable=False),
        sa.Column("artifact_type", sa.String(length=50), nullable=False),
        sa.Column("artifact_id", sa.String(length=255), nullable=False),
        sa.Column("resource_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(length=500), nullable=True),
        sa.Column("url", sa.String(length=1000), nullable=True),
        sa.Column(
            "artifact_metadata",
            postgresql.JSON(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
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
        sa.ForeignKeyConstraint(
            ["thread_id"],
            ["chat_threads.id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("thread_id", "artifact_id", name="uq_thread_artifact"),
    )

    # Create indexes for performance
    op.create_index("idx_thread_artifacts_thread", "thread_artifacts", ["thread_id"], unique=False)
    op.create_index("idx_thread_artifacts_type", "thread_artifacts", ["artifact_type"], unique=False)
    op.create_index(
        "idx_thread_artifacts_resource",
        "thread_artifacts",
        ["artifact_type", "resource_id"],
        unique=False,
    )
    op.create_index(
        "idx_thread_artifacts_created",
        "thread_artifacts",
        [sa.text("created_at DESC")],
        unique=False,
    )


def downgrade() -> None:
    """Drop thread_artifacts table and all indexes."""
    op.drop_index("idx_thread_artifacts_created", table_name="thread_artifacts")
    op.drop_index("idx_thread_artifacts_resource", table_name="thread_artifacts")
    op.drop_index("idx_thread_artifacts_type", table_name="thread_artifacts")
    op.drop_index("idx_thread_artifacts_thread", table_name="thread_artifacts")
    op.drop_table("thread_artifacts")
