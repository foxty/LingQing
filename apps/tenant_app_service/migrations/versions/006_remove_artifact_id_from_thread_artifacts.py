"""Remove artifact_id from thread_artifacts.

Revision ID: 006_rm_artifact_id
Revises: 005_add_thread_artifacts
Create Date: 2026-01-19

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "006_rm_artifact_id"
down_revision = "005_add_thread_artifacts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Remove artifact_id field and update unique constraint."""
    # Drop old unique constraint
    op.drop_constraint("uq_thread_artifact", "thread_artifacts", type_="unique")

    # Drop artifact_id column
    op.drop_column("thread_artifacts", "artifact_id")

    # Add new unique constraint using resource_id
    op.create_unique_constraint(
        "uq_thread_artifact_resource",
        "thread_artifacts",
        ["thread_id", "artifact_type", "resource_id"],
    )


def downgrade() -> None:
    """Restore artifact_id field and old unique constraint."""
    # Drop new constraint
    op.drop_constraint("uq_thread_artifact_resource", "thread_artifacts", type_="unique")

    # Add back artifact_id column
    op.add_column(
        "thread_artifacts",
        sa.Column("artifact_id", sa.String(255), nullable=True),
    )

    # Populate artifact_id with format: {artifact_type}_{resource_id}
    op.execute(
        """
        UPDATE thread_artifacts
        SET artifact_id = artifact_type || '_' || COALESCE(CAST(resource_id AS TEXT), 'none')
        WHERE artifact_id IS NULL
        """
    )

    # Make artifact_id non-nullable
    op.alter_column("thread_artifacts", "artifact_id", nullable=False)

    # Restore old unique constraint
    op.create_unique_constraint("uq_thread_artifact", "thread_artifacts", ["thread_id", "artifact_id"])
