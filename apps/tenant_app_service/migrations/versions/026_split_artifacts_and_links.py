"""Split canonical artifacts from thread links.

Revision ID: 026_split_artifacts_links
Revises: 025_artifacts_decouple
Create Date: 2026-03-27

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "026_split_artifacts_links"
down_revision = "025_artifacts_decouple"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create artifacts/artifact_links and backfill from legacy thread_artifacts."""
    op.create_table(
        "artifacts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column(
            "source_thread_id",
            sa.String(length=255),
            nullable=True,
            comment="Original thread where artifact was generated (optional)",
        ),
        sa.Column("artifact_type", sa.String(length=50), nullable=False),
        sa.Column("resource_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=True),
        sa.Column("url", sa.String(length=1000), nullable=True),
        sa.Column("artifact_metadata", sa.JSON(), nullable=False, server_default="{}"),
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
        sa.UniqueConstraint("tenant_id", "artifact_type", "resource_id", name="uq_artifact_resource"),
    )

    op.create_index("idx_artifacts_type", "artifacts", ["artifact_type"], unique=False)
    op.create_index("idx_artifacts_resource", "artifacts", ["artifact_type", "resource_id"], unique=False)
    op.create_index("idx_artifacts_created", "artifacts", [sa.text("created_at DESC")], unique=False)
    op.create_index(
        "idx_artifacts_user_gallery",
        "artifacts",
        ["tenant_id", "created_by", "created_at"],
        unique=False,
    )

    op.create_table(
        "artifact_links",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("artifact_id", sa.Integer(), nullable=False),
        sa.Column("thread_id", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["artifact_id"], ["artifacts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["thread_id"], ["chat_threads.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("artifact_id", "thread_id", name="uq_artifact_link"),
    )
    op.create_index("idx_artifact_links_thread", "artifact_links", ["thread_id"], unique=False)
    op.create_index("idx_artifact_links_artifact", "artifact_links", ["artifact_id"], unique=False)

    # Backfill canonical artifacts from legacy thread_artifacts.
    op.execute(
        """
        INSERT INTO artifacts (
            tenant_id,
            created_by,
            source_thread_id,
            artifact_type,
            resource_id,
            title,
            url,
            artifact_metadata,
            created_at,
            updated_at
        )
        SELECT DISTINCT ON (ta.tenant_id, ta.artifact_type, ta.resource_id)
            ta.tenant_id,
            ta.created_by,
            ta.thread_id,
            ta.artifact_type,
            ta.resource_id,
            ta.title,
            ta.url,
            COALESCE(ta.artifact_metadata, '{}'::json),
            ta.created_at,
            ta.updated_at
        FROM thread_artifacts ta
        WHERE ta.tenant_id IS NOT NULL
        ORDER BY ta.tenant_id, ta.artifact_type, ta.resource_id, ta.id DESC
        """
    )

    # Backfill artifact-thread links.
    op.execute(
        """
        INSERT INTO artifact_links (artifact_id, thread_id, created_at)
        SELECT a.id, ta.thread_id, ta.created_at
        FROM thread_artifacts ta
        JOIN artifacts a
          ON a.tenant_id = ta.tenant_id
         AND a.artifact_type = ta.artifact_type
         AND a.resource_id = ta.resource_id
        WHERE ta.thread_id IS NOT NULL
        ON CONFLICT (artifact_id, thread_id) DO NOTHING
        """
    )


def downgrade() -> None:
    """Drop split artifact tables."""
    op.drop_index("idx_artifact_links_artifact", table_name="artifact_links")
    op.drop_index("idx_artifact_links_thread", table_name="artifact_links")
    op.drop_table("artifact_links")

    op.drop_index("idx_artifacts_user_gallery", table_name="artifacts")
    op.drop_index("idx_artifacts_created", table_name="artifacts")
    op.drop_index("idx_artifacts_resource", table_name="artifacts")
    op.drop_index("idx_artifacts_type", table_name="artifacts")
    op.drop_table("artifacts")
