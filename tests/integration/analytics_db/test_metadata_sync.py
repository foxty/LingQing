"""Metadata sync / catalog DB managers with URL-encoded ``metadata_sync`` passwords."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.db.models import DataSource, Tenant, User
from apps.shared.external_systems.data_source.repository import AssetMetadataRepository, DataSourceRepository
from apps.shared.external_systems.data_source.service import DataSourceService
from apps.shared.external_systems.domain.types import CREDENTIAL_MODE_USER
from apps.shared.infra.analytics_db.manager_factory import create_db_manager_from_config
from tests.integration.analytics_db.conftest import METADATA_SYNC_PASSWORD
from tests.integration.helpers.analytics_provision import (
    provision_standalone_postgres_database,
    teardown_standalone_postgres_database,
)


@pytest.mark.asyncio
async def test_metadata_sync_db_manager_connects_and_discovers(
    async_db_session: AsyncSession,
    pg_coords,
    monkeypatch,
):
    host, port = pg_coords
    warehouse = await provision_standalone_postgres_database(
        monkeypatch=monkeypatch,
        pg_host=host,
        pg_port=port,
        role_password=METADATA_SYNC_PASSWORD,
    )
    try:
        conn = warehouse["connection"]
        async with create_db_manager_from_config(
            tenant_id=1,
            db_type="postgres",
            config=conn.to_dict(),
            managed=True,
        ) as mgr:
            await mgr.execute("CREATE TABLE catalog_probe (id integer)")
            await mgr.execute("INSERT INTO catalog_probe VALUES (42)")

        suffix = warehouse["suffix"]
        tenant = Tenant(name=f"sync_um_{suffix}", slug=f"sync-um-{suffix}", status="active")
        async_db_session.add(tenant)
        await async_db_session.flush()

        user = User(
            username=f"sync_owner_{suffix}",
            email=f"sync_owner_{suffix}@test.local",
            hashed_password="hashed",
            tenant_id=tenant.id,
            role="admin",
            status="active",
        )
        async_db_session.add(user)
        await async_db_session.flush()

        data_source = DataSource(
            tenant_id=tenant.id,
            owner_id=user.id,
            name=f"user_sync_{suffix}",
            type="postgres",
            managed=False,
            credential_mode=CREDENTIAL_MODE_USER,
            config={
                "host": conn.host,
                "port": conn.port,
                "database": conn.database,
                "metadata_sync": {
                    "username": conn.username,
                    "password": conn.password,
                },
            },
        )
        async_db_session.add(data_source)
        await async_db_session.flush()

        ds_service = DataSourceService(
            tenant_id=tenant.id,
            data_source_repo=DataSourceRepository(async_db_session),
            asset_repo=AssetMetadataRepository(async_db_session),
        )

        db_manager = await ds_service.get_db_manager_for_metadata_sync(data_source.id)
        async with db_manager as mgr:
            ok, message = await mgr.test_connection()
            assert ok, message
            assets, total = await mgr.discover_assets(query="catalog_probe")
        assert total >= 1
        assert any(a.name == "catalog_probe" for a in assets)
    finally:
        await teardown_standalone_postgres_database(warehouse)