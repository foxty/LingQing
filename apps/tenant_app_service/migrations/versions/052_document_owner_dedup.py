"""Add unique constraint to documents table for owner-scoped deduplication.

Revision ID: 052_document_owner_dedup
Revises: 051_add_source_parser
Create Date: 2026-05-16 15:30:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "052_document_owner_dedup"
down_revision: Union[str, None] = "051_add_source_parser"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Make file_hash NOT NULL (it's always set during upload)
    op.alter_column(
        "documents",
        "file_hash",
        existing_type=sa.String(64),
        nullable=False,
        comment="SHA256 hash for deduplication",
    )

    # Add index on file_hash for faster dedup checks
    op.create_index(
        "ix_documents_file_hash",
        "documents",
        ["file_hash"],
    )

    # Add unique constraint for owner-scoped deduplication
    # Prevents same user from uploading same file content twice
    op.create_unique_constraint(
        "uq_document_tenant_owner_hash",
        "documents",
        ["tenant_id", "owner_id", "file_hash"],
    )


def downgrade() -> None:
    # Remove unique constraint
    op.drop_constraint(
        "uq_document_tenant_owner_hash",
        "documents",
        type_="unique",
    )

    # Remove index
    op.drop_index("ix_documents_file_hash", "documents")

    # Revert file_hash to nullable
    op.alter_column(
        "documents",
        "file_hash",
        existing_type=sa.String(64),
        nullable=True,
        comment=None,
    )
