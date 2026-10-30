"""Normalize resource_index.source_parser to docling.

Revision ID: 080_parser_default_to_docling
Revises: 079_thread_runs
Create Date: 2026-10-30

Relabel legacy default parser rows; does not reparse documents or change stored blocks.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "080_parser_default_to_docling"
down_revision: Union[str, None] = "079_thread_runs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE resource_index SET source_parser = 'docling' WHERE source_parser = 'default'",
        ),
    )
    op.alter_column(
        "resource_index",
        "source_parser",
        server_default="docling",
        existing_type=sa.String(50),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "resource_index",
        "source_parser",
        server_default="default",
        existing_type=sa.String(50),
        existing_nullable=False,
    )
    op.execute(
        sa.text(
            "UPDATE resource_index SET source_parser = 'default' WHERE source_parser = 'docling'",
        ),
    )
