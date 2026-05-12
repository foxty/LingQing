"""Add timestamp column to chat_messages table.

Revision ID: 002
Revises: 001
Create Date: 2025-01-03

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: Add timestamp column to chat_messages."""
    # Add timestamp column (nullable initially to handle existing data)
    op.add_column(
        "chat_messages",
        sa.Column(
            "timestamp",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Message timestamp when created in conversation",
        ),
    )

    # Migrate existing data: Set timestamp to created_at for all existing messages
    op.execute("UPDATE chat_messages SET timestamp = created_at WHERE timestamp IS NULL")

    # Now make the column NOT NULL
    op.alter_column(
        "chat_messages",
        "timestamp",
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
    )

    # Add index on timestamp for efficient queries
    op.create_index("idx_chat_messages_timestamp", "chat_messages", ["timestamp"])


def downgrade() -> None:
    """Downgrade schema: Remove timestamp column."""
    # Drop index
    op.drop_index("idx_chat_messages_timestamp", table_name="chat_messages")

    # Drop column
    op.drop_column("chat_messages", "timestamp")
