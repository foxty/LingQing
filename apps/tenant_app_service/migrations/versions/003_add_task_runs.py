"""Add task_runs table with entity sync tracking.

Revision ID: 003_add_task_runs
Revises: 002_add_timestamp_to_chat_messages
Create Date: 2026-01-16

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "003_add_task_runs"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add sync tracking fields to data_sources
    op.add_column(
        "data_sources",
        sa.Column(
            "last_metadata_synced_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Last successful metadata sync from source database",
        ),
    )
    op.add_column(
        "data_sources",
        sa.Column(
            "last_metadata_sync_error",
            sa.Text(),
            nullable=True,
            comment="Last metadata sync error message",
        ),
    )
    op.add_column(
        "data_sources",
        sa.Column(
            "last_vector_synced_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Last successful vector index sync",
        ),
    )
    op.add_column(
        "data_sources",
        sa.Column(
            "last_vector_sync_error",
            sa.Text(),
            nullable=True,
            comment="Last vector sync error message",
        ),
    )

    # Add sync tracking fields to asset_metadata
    op.add_column(
        "asset_metadata",
        sa.Column(
            "last_metadata_synced_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Last successful metadata sync",
        ),
    )
    op.add_column(
        "asset_metadata",
        sa.Column(
            "last_vector_synced_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Last successful vector sync",
        ),
    )

    # Add sync tracking fields to documents
    op.add_column(
        "documents",
        sa.Column(
            "last_vector_synced_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Last successful vector sync",
        ),
    )

    # Drop vector_sync_status table (replaced by task_runs + entity-level tracking)
    op.drop_table("vector_sync_status")

    # Create task_runs table
    op.create_table(
        "task_runs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "task_type",
            sa.String(length=50),
            nullable=False,
            comment="vector_sync, asset_sync, cleanup, etc.",
        ),
        sa.Column("task_name", sa.String(length=100), nullable=False, comment="Human-readable task name"),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            comment="pending, running, success, failed",
        ),
        sa.Column("trigger", sa.String(length=20), nullable=False, comment="manual, scheduled"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "result",
            sa.JSON(),
            nullable=False,
            server_default="{}",
            comment="Task execution result: return value from task function",
        ),
        sa.Column(
            "input_params",
            sa.JSON(),
            nullable=False,
            server_default="{}",
            comment="Task input parameters for audit/replay",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create indexes
    op.create_index("idx_task_runs_type_started", "task_runs", ["task_type", "started_at"])
    op.create_index("idx_task_runs_status", "task_runs", ["status"])


def downgrade() -> None:
    # Drop task_runs table
    op.drop_index("idx_task_runs_status", "task_runs")
    op.drop_index("idx_task_runs_type_started", "task_runs")
    op.drop_table("task_runs")

    # Recreate vector_sync_status table
    op.create_table(
        "vector_sync_status",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("sync_type", sa.String(length=50), nullable=False, comment="documents or assets"),
        sa.Column(
            "last_sync_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "last_sync_status",
            sa.String(length=20),
            nullable=False,
            server_default="success",
            comment="success, failed, or partial",
        ),
        sa.Column(
            "sync_counter",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="Incremental sync count",
        ),
        sa.Column(
            "last_verified_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Last consistency verification timestamp",
        ),
        sa.Column(
            "inconsistency_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="Historical inconsistency count",
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
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "sync_type", name="uq_vector_sync_tenant_type"),
    )
    op.create_index("idx_vector_sync_tenant_type", "vector_sync_status", ["tenant_id", "sync_type"])

    # Remove sync tracking fields from documents
    op.drop_column("documents", "last_vector_synced_at")

    # Remove sync tracking fields from asset_metadata
    op.drop_column("asset_metadata", "last_vector_synced_at")
    op.drop_column("asset_metadata", "last_metadata_synced_at")

    # Remove sync tracking fields from data_sources
    op.drop_column("data_sources", "last_vector_sync_error")
    op.drop_column("data_sources", "last_vector_synced_at")
    op.drop_column("data_sources", "last_metadata_sync_error")
    op.drop_column("data_sources", "last_metadata_synced_at")
