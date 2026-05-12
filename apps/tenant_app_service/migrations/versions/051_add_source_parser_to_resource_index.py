"""Add source_parser column to resource_index table.

Revision ID: 051_add_source_parser
Revises: 050_jieba_fts_tokenization
Create Date: 2026-05-15 11:15:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "051_add_source_parser"
down_revision: Union[str, None] = "050_jieba_fts_tokenization"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add source_parser column with default value "default"
    op.add_column(
        "resource_index",
        sa.Column(
            "source_parser",
            sa.String(50),
            nullable=False,
            server_default="default",
            comment="Parser used to generate raw_content: default, docling, mineru, etc.",
        ),
    )
    # Create index for filtering by parser type
    op.create_index(
        "idx_resource_index_source_parser",
        "resource_index",
        ["tenant_id", "source_parser"],
    )


def downgrade() -> None:
    # Drop index first, then column
    op.drop_index("idx_resource_index_source_parser", table_name="resource_index")
    op.drop_column("resource_index", "source_parser")
