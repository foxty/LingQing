"""Add missing documents.last_vector_sync_error column.

Revision ID: 020_doc_vec_sync_err
Revises: 019_add_hitl_approvals
Create Date: 2026-03-13
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "020_doc_vec_sync_err"
down_revision = "019_add_hitl_approvals"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add missing vector sync error field to documents table."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = {col["name"] for col in inspector.get_columns("documents")}

    if "last_vector_sync_error" not in existing_columns:
        op.add_column(
            "documents",
            sa.Column(
                "last_vector_sync_error",
                sa.Text(),
                nullable=True,
                comment="Last vector sync error message",
            ),
        )


def downgrade() -> None:
    """Remove vector sync error field from documents table."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = {col["name"] for col in inspector.get_columns("documents")}

    if "last_vector_sync_error" in existing_columns:
        op.drop_column("documents", "last_vector_sync_error")
