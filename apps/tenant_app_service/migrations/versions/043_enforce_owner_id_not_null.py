"""Enforce non-null owner_id for core resources.

Revision ID: 043_owner_not_null
Revises: 042_api_owner_cols
Create Date: 2026-04-27
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "043_owner_not_null"
down_revision = "042_api_owner_cols"
branch_labels = None
depends_on = None


def _backfill_owner_ids() -> None:
    # Core resource owners: fallback to first tenant user when missing.
    op.execute(
        sa.text(
            """
            UPDATE documents
            SET owner_id = (
                SELECT u.id
                FROM users u
                WHERE u.tenant_id = documents.tenant_id
                ORDER BY u.id
                LIMIT 1
            )
            WHERE owner_id IS NULL
            """
        )
    )

    op.execute(
        sa.text(
            """
            UPDATE data_sources
            SET owner_id = (
                SELECT u.id
                FROM users u
                WHERE u.tenant_id = data_sources.tenant_id
                ORDER BY u.id
                LIMIT 1
            )
            WHERE owner_id IS NULL
            """
        )
    )

    op.execute(
        sa.text(
            """
            UPDATE live_apps
            SET owner_id = (
                SELECT u.id
                FROM users u
                WHERE u.tenant_id = live_apps.tenant_id
                ORDER BY u.id
                LIMIT 1
            )
            WHERE owner_id IS NULL
            """
        )
    )

    op.execute(
        sa.text(
            """
            UPDATE api_connectors
            SET owner_id = (
                SELECT u.id
                FROM users u
                WHERE u.tenant_id = api_connectors.tenant_id
                ORDER BY u.id
                LIMIT 1
            )
            WHERE owner_id IS NULL
            """
        )
    )

    # Prefer connector owner for operations, then tenant fallback.
    op.execute(
        sa.text(
            """
            UPDATE api_operation_index
            SET owner_id = (
                SELECT c.owner_id
                FROM api_connectors c
                WHERE c.id = api_operation_index.connector_id
            )
            WHERE owner_id IS NULL
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE api_operation_index
            SET owner_id = (
                SELECT u.id
                FROM users u
                WHERE u.tenant_id = api_operation_index.tenant_id
                ORDER BY u.id
                LIMIT 1
            )
            WHERE owner_id IS NULL
            """
        )
    )

    # Prefer data source owner for assets, then tenant fallback.
    op.execute(
        sa.text(
            """
            UPDATE asset_metadata
            SET owner_id = (
                SELECT ds.owner_id
                FROM data_sources ds
                WHERE ds.id = asset_metadata.data_source_id
            )
            WHERE owner_id IS NULL
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE asset_metadata
            SET owner_id = (
                SELECT u.id
                FROM users u
                JOIN data_sources ds ON ds.tenant_id = u.tenant_id
                WHERE ds.id = asset_metadata.data_source_id
                ORDER BY u.id
                LIMIT 1
            )
            WHERE owner_id IS NULL
            """
        )
    )

    op.execute(
        sa.text(
            """
            UPDATE scheduled_tasks
            SET owner_id = user_id
            WHERE owner_id IS NULL
            """
        )
    )

    op.execute(
        sa.text(
            """
            UPDATE dashboards
            SET owner_id = (
                SELECT u.id
                FROM users u
                WHERE u.tenant_id = dashboards.tenant_id
                ORDER BY u.id
                LIMIT 1
            )
            WHERE owner_id IS NULL
            """
        )
    )

    op.execute(
        sa.text(
            """
            UPDATE artifacts
            SET owner_id = (
                SELECT u.id
                FROM users u
                WHERE u.tenant_id = artifacts.tenant_id
                ORDER BY u.id
                LIMIT 1
            )
            WHERE owner_id IS NULL
            """
        )
    )

    op.execute(
        sa.text(
            """
            UPDATE reports
            SET owner_id = (
                SELECT u.id
                FROM users u
                WHERE u.tenant_id = reports.tenant_id
                ORDER BY u.id
                LIMIT 1
            )
            WHERE owner_id IS NULL
            """
        )
    )

    # Resource ACL owner derives from resource owner when possible.
    op.execute(
        sa.text(
            """
            UPDATE resource_acl
            SET owner_id = (
                SELECT d.owner_id
                FROM documents d
                WHERE resource_acl.resource_type = 'document'
                  AND d.id = resource_acl.resource_id
            )
            WHERE owner_id IS NULL
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE resource_acl
            SET owner_id = (
                SELECT a.owner_id
                FROM asset_metadata a
                WHERE resource_acl.resource_type IN ('asset_metadata', 'asset')
                  AND a.id = resource_acl.resource_id
            )
            WHERE owner_id IS NULL
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE resource_acl
            SET owner_id = (
                SELECT c.owner_id
                FROM api_connectors c
                WHERE resource_acl.resource_type = 'api_connector'
                  AND c.id = resource_acl.resource_id
            )
            WHERE owner_id IS NULL
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE resource_acl
            SET owner_id = (
                SELECT da.owner_id
                FROM dashboards da
                WHERE resource_acl.resource_type = 'dashboard'
                  AND da.id = resource_acl.resource_id
            )
            WHERE owner_id IS NULL
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE resource_acl
            SET owner_id = (
                SELECT r.owner_id
                FROM reports r
                WHERE resource_acl.resource_type = 'report'
                  AND r.id = resource_acl.resource_id
            )
            WHERE owner_id IS NULL
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE resource_acl
            SET owner_id = (
                SELECT st.owner_id
                FROM scheduled_tasks st
                WHERE resource_acl.resource_type = 'scheduled_task'
                  AND st.id = resource_acl.resource_id
            )
            WHERE owner_id IS NULL
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE resource_acl
            SET owner_id = (
                SELECT la.owner_id
                FROM live_apps la
                WHERE resource_acl.resource_type = 'app'
                  AND la.id = resource_acl.resource_id
            )
            WHERE owner_id IS NULL
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE resource_acl
            SET owner_id = (
                SELECT u.id
                FROM users u
                WHERE u.tenant_id = resource_acl.tenant_id
                ORDER BY u.id
                LIMIT 1
            )
            WHERE owner_id IS NULL
            """
        )
    )


def upgrade() -> None:
    _backfill_owner_ids()

    op.alter_column("documents", "owner_id", existing_type=sa.Integer(), nullable=False)
    op.alter_column("data_sources", "owner_id", existing_type=sa.Integer(), nullable=False)
    op.alter_column("live_apps", "owner_id", existing_type=sa.Integer(), nullable=False)
    op.alter_column("api_connectors", "owner_id", existing_type=sa.Integer(), nullable=False)
    op.alter_column("api_operation_index", "owner_id", existing_type=sa.Integer(), nullable=False)
    op.alter_column("asset_metadata", "owner_id", existing_type=sa.Integer(), nullable=False)
    op.alter_column("scheduled_tasks", "owner_id", existing_type=sa.Integer(), nullable=False)
    op.alter_column("dashboards", "owner_id", existing_type=sa.Integer(), nullable=False)
    op.alter_column("artifacts", "owner_id", existing_type=sa.Integer(), nullable=False)
    op.alter_column("reports", "owner_id", existing_type=sa.Integer(), nullable=False)
    op.alter_column("resource_acl", "owner_id", existing_type=sa.Integer(), nullable=False)


def downgrade() -> None:
    op.alter_column("resource_acl", "owner_id", existing_type=sa.Integer(), nullable=True)
    op.alter_column("reports", "owner_id", existing_type=sa.Integer(), nullable=True)
    op.alter_column("artifacts", "owner_id", existing_type=sa.Integer(), nullable=True)
    op.alter_column("dashboards", "owner_id", existing_type=sa.Integer(), nullable=True)
    op.alter_column("scheduled_tasks", "owner_id", existing_type=sa.Integer(), nullable=True)
    op.alter_column("asset_metadata", "owner_id", existing_type=sa.Integer(), nullable=True)
    op.alter_column("api_operation_index", "owner_id", existing_type=sa.Integer(), nullable=True)
    op.alter_column("api_connectors", "owner_id", existing_type=sa.Integer(), nullable=True)
    op.alter_column("live_apps", "owner_id", existing_type=sa.Integer(), nullable=True)
    op.alter_column("data_sources", "owner_id", existing_type=sa.Integer(), nullable=True)
    op.alter_column("documents", "owner_id", existing_type=sa.Integer(), nullable=True)
