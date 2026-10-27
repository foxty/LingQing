"""Unit tests for registered-asset SQL whitelist (real metadata lookup)."""

import pandas as pd
import pytest

from apps.shared.core.exceptions import AuthorizationError
from apps.shared.dashboard.domain import DashboardWidget, WidgetPosition
from apps.shared.dashboard.service import DashboardService
from apps.shared.data_source.repository import AssetMetadataRepository, DataSourceRepository
from apps.shared.data_source.service import DataSourceService
from apps.shared.domain.actor import ActorContext
from tests.helpers.data_source_fixtures import (
    create_asset,
    create_data_source,
    create_tenant_user,
    seed_data_source_owner_policies,
)

_INFORMATION_SCHEMA_SQL = (
    "SELECT table_schema, table_name, table_type FROM information_schema.tables "
    "WHERE table_schema NOT IN ('pg_catalog', 'information_schema') "
    "ORDER BY table_schema, table_name"
)


async def _service(session, tenant_id: int) -> DataSourceService:
    return DataSourceService(
        tenant_id=tenant_id,
        data_source_repo=DataSourceRepository(session),
        asset_repo=AssetMetadataRepository(session),
    )


class _FakeDBManager:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def query(self, sql: str, params=None):
        return pd.DataFrame([{"ok": 1}])


@pytest.mark.asyncio
async def test_require_registered_assets_denies_information_schema_without_asset(async_db_session):
    tenant, owner = await create_tenant_user(async_db_session, tenant_name="wl-t1", username="wl-owner")
    await seed_data_source_owner_policies(async_db_session, tenant.id, base_id=9100)
    data_source = await create_data_source(async_db_session, tenant_id=tenant.id, owner_id=owner.id)
    await create_asset(
        async_db_session,
        data_source_id=data_source.id,
        owner_id=owner.id,
        asset_name="orders",
    )

    service = await _service(async_db_session, tenant.id)
    with pytest.raises(AuthorizationError, match="unregistered asset 'information_schema.tables'"):
        await service.require_registered_assets_in_sql(
            data_source_id=data_source.id,
            sql_query=_INFORMATION_SCHEMA_SQL,
        )


@pytest.mark.asyncio
async def test_require_registered_assets_asset_named_tables_does_not_authorize_information_schema(
    async_db_session,
):
    tenant, owner = await create_tenant_user(async_db_session, tenant_name="wl-t2", username="wl-owner2")
    await seed_data_source_owner_policies(async_db_session, tenant.id, base_id=9200)
    data_source = await create_data_source(async_db_session, tenant_id=tenant.id, owner_id=owner.id)
    await create_asset(
        async_db_session,
        data_source_id=data_source.id,
        owner_id=owner.id,
        asset_name="tables",
    )

    service = await _service(async_db_session, tenant.id)
    with pytest.raises(AuthorizationError, match="information_schema.tables"):
        await service.require_registered_assets_in_sql(
            data_source_id=data_source.id,
            sql_query=_INFORMATION_SCHEMA_SQL,
        )


@pytest.mark.asyncio
async def test_query_data_for_actor_allows_schema_qualified_business_table(async_db_session, monkeypatch):
    tenant, owner = await create_tenant_user(async_db_session, tenant_name="wl-t3", username="wl-owner3")
    await seed_data_source_owner_policies(async_db_session, tenant.id, base_id=9300)
    data_source = await create_data_source(async_db_session, tenant_id=tenant.id, owner_id=owner.id)
    await create_asset(
        async_db_session,
        data_source_id=data_source.id,
        owner_id=owner.id,
        asset_name="orders",
    )

    service = await _service(async_db_session, tenant.id)
    actor = ActorContext(tenant_id=tenant.id, user_id=owner.id, user_role="admin")

    async def _fake_get_db_manager(_self, _data_source_id: int):
        return _FakeDBManager()

    monkeypatch.setattr(DataSourceService, "get_db_manager", _fake_get_db_manager)

    await service.query_data_for_actor(
        data_source_id=data_source.id,
        sql_query="SELECT * FROM analytics.orders",
        actor=actor,
    )


@pytest.mark.asyncio
async def test_query_data_for_actor_denies_unregistered_table_with_real_metadata(async_db_session, monkeypatch):
    tenant, owner = await create_tenant_user(async_db_session, tenant_name="wl-t4", username="wl-owner4")
    await seed_data_source_owner_policies(async_db_session, tenant.id, base_id=9400)
    data_source = await create_data_source(async_db_session, tenant_id=tenant.id, owner_id=owner.id)
    await create_asset(
        async_db_session,
        data_source_id=data_source.id,
        owner_id=owner.id,
        asset_name="orders",
    )

    service = await _service(async_db_session, tenant.id)
    actor = ActorContext(tenant_id=tenant.id, user_id=owner.id, user_role="admin")

    async def _fake_get_db_manager(_self, _data_source_id: int):
        return _FakeDBManager()

    monkeypatch.setattr(DataSourceService, "get_db_manager", _fake_get_db_manager)

    with pytest.raises(AuthorizationError, match="unregistered asset 'secret_table'"):
        await service.query_data_for_actor(
            data_source_id=data_source.id,
            sql_query="SELECT * FROM secret_table",
            actor=actor,
        )


@pytest.mark.asyncio
async def test_prepare_widget_analytics_query_denies_information_schema_with_real_whitelist(
    async_db_session,
    monkeypatch,
):
    tenant, owner = await create_tenant_user(async_db_session, tenant_name="wl-t5", username="wl-owner5")
    await seed_data_source_owner_policies(async_db_session, tenant.id, base_id=9500)
    data_source = await create_data_source(async_db_session, tenant_id=tenant.id, owner_id=owner.id)
    await create_asset(
        async_db_session,
        data_source_id=data_source.id,
        owner_id=owner.id,
        asset_name="orders",
    )

    data_source_service = await _service(async_db_session, tenant.id)
    dashboard_service = DashboardService.create(tenant_id=tenant.id, db_session=async_db_session)
    widget = DashboardWidget(
        id="w1",
        type="table",
        position=WidgetPosition(x=0, y=0, w=4, h=3),
        query=_INFORMATION_SCHEMA_SQL,
        data_source_id=data_source.id,
    )

    async def _fake_get_db_manager(_self, _data_source_id: int):
        raise AssertionError("warehouse must not run when whitelist fails")

    monkeypatch.setattr(DataSourceService, "get_db_manager", _fake_get_db_manager)

    with pytest.raises(AuthorizationError, match="information_schema.tables"):
        await dashboard_service.prepare_widget_analytics_query(
            widget,
            data_source_service=data_source_service,
            user_id=owner.id,
            user_role="admin",
        )


def test_table_ref_lookup_candidates_skips_suffix_for_system_catalog():
    candidates = DataSourceService._table_ref_lookup_candidates("information_schema.tables")
    assert set(candidates) == {"information_schema.tables"}
    assert "tables" not in candidates

    business = DataSourceService._table_ref_lookup_candidates("analytics.orders")
    assert "orders" in business
