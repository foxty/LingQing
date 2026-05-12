"""Fix datetime columns to use TIMESTAMP WITH TIME ZONE.

Revision ID: 023
Revises: 022
Create Date: 2026-03-23

Background
----------
Several tables were created in migration 001 with ``sa.DateTime()``
(i.e. ``TIMESTAMP WITHOUT TIME ZONE``) while the ORM models already
declare those columns as ``DateTime(timezone=True)``.

The sync-tracking columns added later (``last_vector_synced_at`` in 003,
others in subsequent migrations) were correctly created as
``TIMESTAMP WITH TIME ZONE``.

This mismatch causes PostgreSQL to compare TIMESTAMP vs TIMESTAMPTZ
by implicitly casting the naive value using the *session timezone*.
If the server timezone is not UTC the comparison ``updated_at >
last_vector_synced_at`` can produce incorrect results, causing every
document/asset to be re-queued on every incremental sync run.

Fix: convert ALL affected columns to TIMESTAMPTZ, interpreting stored
values as UTC (the only timezone ever written by application code).
No separate UPDATE statements are needed — PostgreSQL rewrites the
column values inline via the USING clause.

No CRUD code changes are required:
- All writes already use datetime.now(timezone.utc).
- All reads call .isoformat() before serialisation; the output gains a
  "+00:00" suffix which is valid ISO 8601 and handled by all clients.

Affected tables (created in migration 001)
------------------------------------------
documents            : upload_date, created_at, updated_at
asset_metadata       : created_at, updated_at
data_sources         : created_at, updated_at
tenants              : created_at, updated_at
users                : created_at, updated_at, last_login_at
agents               : created_at, updated_at
chat_threads         : created_at, updated_at
chat_messages        : created_at
temp_table_metadata  : created_at, expires_at
agent_metrics_events : timestamp, created_at, start_time, end_time

Note: vector_sync_status was dropped in migration 003 — excluded.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "023_fix_datetime_tz"
down_revision: Union[str, None] = "022_artifact_gallery"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (table, column) pairs created as TIMESTAMP WITHOUT TIME ZONE in migration 001
_COLUMNS: list[tuple[str, str]] = [
    # Core domain tables (also fix the sync-comparison columns here)
    ("documents", "upload_date"),
    ("documents", "created_at"),
    ("documents", "updated_at"),
    ("asset_metadata", "created_at"),
    ("asset_metadata", "updated_at"),
    ("data_sources", "created_at"),
    ("data_sources", "updated_at"),
    ("tenants", "created_at"),
    ("tenants", "updated_at"),
    ("users", "created_at"),
    ("users", "updated_at"),
    ("users", "last_login_at"),
    ("agents", "created_at"),
    ("agents", "updated_at"),
    # Conversation tables
    ("chat_threads", "created_at"),
    ("chat_threads", "updated_at"),
    ("chat_messages", "created_at"),
    # Workspace / analytics tables
    ("temp_table_metadata", "created_at"),
    ("temp_table_metadata", "expires_at"),
    ("agent_metrics_events", "timestamp"),
    ("agent_metrics_events", "created_at"),
    ("agent_metrics_events", "start_time"),
    ("agent_metrics_events", "end_time"),
]


def upgrade() -> None:
    """Convert TIMESTAMP (without TZ) columns to TIMESTAMPTZ."""
    for table, column in _COLUMNS:
        op.alter_column(
            table,
            column,
            type_=sa.DateTime(timezone=True),
            postgresql_using=f"{column} AT TIME ZONE 'UTC'",
        )


def downgrade() -> None:
    """Revert TIMESTAMPTZ columns back to TIMESTAMP (without TZ)."""
    for table, column in _COLUMNS:
        op.alter_column(
            table,
            column,
            type_=sa.DateTime(timezone=False),
            postgresql_using=f"{column} AT TIME ZONE 'UTC'",
        )
