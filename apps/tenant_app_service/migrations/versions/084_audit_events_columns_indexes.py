"""Extend audit_events with mandatory columns and query indexes.

Revision ID: 084_audit_events_columns_indexes
Revises: 083_user_integration_credentials
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "084_audit_events_columns_indexes"
down_revision = "083_user_integration_credentials"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("audit_events", sa.Column("actor_type", sa.String(length=32), nullable=True))
    op.add_column("audit_events", sa.Column("outcome", sa.String(length=16), nullable=True))
    op.add_column("audit_events", sa.Column("client_ip", sa.String(length=64), nullable=True))
    op.add_column("audit_events", sa.Column("user_agent", sa.String(length=512), nullable=True))
    op.add_column("audit_events", sa.Column("request_id", sa.String(length=100), nullable=True))
    op.add_column("audit_events", sa.Column("resource_type", sa.String(length=64), nullable=True))
    op.add_column("audit_events", sa.Column("resource_id", sa.String(length=128), nullable=True))
    op.create_index(
        "idx_audit_events_tenant_actor_created",
        "audit_events",
        ["tenant_id", "actor_user_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "idx_audit_events_tenant_event_type_created",
        "audit_events",
        ["tenant_id", "event_type", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_audit_events_tenant_event_type_created", table_name="audit_events")
    op.drop_index("idx_audit_events_tenant_actor_created", table_name="audit_events")
    op.drop_column("audit_events", "resource_id")
    op.drop_column("audit_events", "resource_type")
    op.drop_column("audit_events", "request_id")
    op.drop_column("audit_events", "user_agent")
    op.drop_column("audit_events", "client_ip")
    op.drop_column("audit_events", "outcome")
    op.drop_column("audit_events", "actor_type")