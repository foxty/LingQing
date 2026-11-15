"""Asset sync orchestration: user-mode data sources need metadata_sync to be included."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.db.models import DataSource, Tenant, User
from apps.shared.external_systems.data_source.asset_metadata_service import AssetMetadataService
from apps.shared.external_systems.data_source.service import DataSourceService
from apps.shared.tasks.system.jobs.asset_sync import _sync_tenant_assets
from tests.integration.tool_integration_helpers import SessionContext

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def patch_asset_sync_app_db(async_db_session, monkeypatch):
    """Route asset_sync job DB access through the integration Postgres session."""

    def _app_db_session():
        return SessionContext(async_db_session)

    monkeypatch.setattr(
        "apps.shared.tasks.system.jobs.asset_sync.app_db_session",
        _app_db_session,
    )


@pytest_asyncio.fixture
async def tenant_with_external_sources(async_db_session: AsyncSession):
    suffix = uuid4().hex[:8]
    tenant = Tenant(name=f"asset_sync_um_{suffix}", slug=f"asset-sync-um-{suffix}", status="active")
    async_db_session.add(tenant)
    await async_db_session.flush()

    user = User(
        username=f"owner_{suffix}",
        email=f"owner_{suffix}@example.com",
        hashed_password="hashed",
        role="admin",
        tenant_id=tenant.id,
        status="active",
    )
    async_db_session.add(user)
    await async_db_session.flush()

    shared = DataSource(
        name=f"shared_pg_{suffix}",
        type="postgres",
        tenant_id=tenant.id,
        owner_id=user.id,
        managed=False,
        credential_mode="shared",
        config={"host": "h1", "database": "db"},
    )
    user_no_sync = DataSource(
        name=f"user_no_sync_{suffix}",
        type="postgres",
        tenant_id=tenant.id,
        owner_id=user.id,
        managed=False,
        credential_mode="user",
        config={"host": "h2", "database": "db"},
    )
    user_with_sync = DataSource(
        name=f"user_sync_{suffix}",
        type="postgres",
        tenant_id=tenant.id,
        owner_id=user.id,
        managed=False,
        credential_mode="user",
        config={
            "host": "h3",
            "database": "db",
            "metadata_sync": {"username": "sync_u", "password": "sync_p"},
        },
    )
    async_db_session.add_all([shared, user_no_sync, user_with_sync])
    await async_db_session.flush()

    return {
        "tenant": tenant,
        "shared_id": shared.id,
        "user_no_sync_id": user_no_sync.id,
        "user_with_sync_id": user_with_sync.id,
    }


async def test_sync_tenant_resolves_shared_and_user_with_metadata_sync(tenant_with_external_sources):
    tenant_id = tenant_with_external_sources["tenant"].id
    shared_id = tenant_with_external_sources["shared_id"]
    user_with_sync_id = tenant_with_external_sources["user_with_sync_id"]

    get_shared = AsyncMock(side_effect=lambda ds_id: f"mgr-shared-{ds_id}")
    get_metadata_sync = AsyncMock(side_effect=lambda ds_id: f"mgr-sync-{ds_id}")
    sync_all = AsyncMock(
        return_value={
            "status": "success",
            "updated_count": 0,
            "skipped_count": 0,
            "error_count": 0,
        }
    )

    with (
        patch.object(DataSourceService, "get_db_manager", get_shared),
        patch.object(DataSourceService, "get_db_manager_for_metadata_sync", get_metadata_sync),
        patch.object(AssetMetadataService, "sync_all_assets", sync_all),
    ):
        result = await _sync_tenant_assets(tenant_id)

    assert result["status"] == "success"
    assert result["skipped_user_mode"] == 1
    assert get_metadata_sync.await_count == 1
    get_metadata_sync.assert_awaited_with(user_with_sync_id)
    assert {c.args[0] for c in get_shared.await_args_list} == {shared_id}
    sync_all.assert_awaited_once()
    call_kwargs = sync_all.await_args.kwargs
    assert set(call_kwargs["data_source_ids"]) == {shared_id, user_with_sync_id}
    assert call_kwargs["db_managers"] == {
        shared_id: f"mgr-shared-{shared_id}",
        user_with_sync_id: f"mgr-sync-{user_with_sync_id}",
    }
