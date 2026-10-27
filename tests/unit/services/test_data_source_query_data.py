"""Unit tests for DataSourceService.query_data authorization flow."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pandas as pd
import pytest

from apps.shared.core.exceptions import AuthorizationError, ValidationError
from apps.shared.data_source.service import DataSourceService
from apps.shared.domain.actor import ActorContext


class _FakeDBManager:
    def __init__(self, df: pd.DataFrame):
        self.df = df
        self.calls: list[tuple[str, dict | None]] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def query(self, sql: str, params: dict | None = None) -> pd.DataFrame:
        self.calls.append((sql, params))
        return self.df


def _service_with_asset_lookup(
    *,
    get_by_data_source_and_name: AsyncMock | None = None,
) -> DataSourceService:
    lookup = get_by_data_source_and_name or AsyncMock(return_value=None)
    return DataSourceService(
        tenant_id=1,
        data_source_repo=SimpleNamespace(),
        asset_repo=SimpleNamespace(get_by_data_source_and_name=lookup, db=object()),
    )


def _patch_query_execution(monkeypatch, service: DataSourceService, df: pd.DataFrame) -> _FakeDBManager:
    fake_manager = _FakeDBManager(df)
    monkeypatch.setattr(service, "get_db_manager", AsyncMock(return_value=fake_manager))
    monkeypatch.setattr(service, "require_read_access_for_actor", AsyncMock(return_value=SimpleNamespace()))
    return fake_manager


@pytest.mark.asyncio
async def test_query_data_rejects_non_select_sql():
    service = _service_with_asset_lookup()
    actor = ActorContext(tenant_id=1, user_id=1, user_role="member")

    with pytest.raises(ValidationError, match="read-only SELECT"):
        await service.query_data_for_actor(data_source_id=1, sql_query="UPDATE orders SET amount = 1", actor=actor)


@pytest.mark.asyncio
async def test_query_data_denies_when_data_source_read_denied(monkeypatch):
    service = _service_with_asset_lookup()
    actor = ActorContext(tenant_id=1, user_id=123, user_role="member")

    monkeypatch.setattr(
        service,
        "require_read_access_for_actor",
        AsyncMock(side_effect=AuthorizationError("无权访问该数据源")),
    )

    with pytest.raises(AuthorizationError, match="无权访问该数据源"):
        await service.query_data_for_actor(data_source_id=1, sql_query="SELECT * FROM orders", actor=actor)


@pytest.mark.asyncio
async def test_query_data_denies_unregistered_asset(monkeypatch):
    lookup = AsyncMock(return_value=None)
    service = _service_with_asset_lookup(get_by_data_source_and_name=lookup)
    actor = ActorContext(tenant_id=1, user_id=123, user_role="member")
    _patch_query_execution(monkeypatch, service, pd.DataFrame([{"id": 1}]))

    with pytest.raises(AuthorizationError, match="unregistered asset 'orders'"):
        await service.query_data_for_actor(
            data_source_id=1,
            sql_query="SELECT * FROM orders",
            actor=actor,
        )

    lookup.assert_awaited()
    assert lookup.await_count >= 1


@pytest.mark.asyncio
async def test_query_data_allows_and_executes_when_asset_registered(monkeypatch):
    registered = SimpleNamespace(id=11, asset_name="orders")
    lookup = AsyncMock(return_value=registered)
    service = _service_with_asset_lookup(get_by_data_source_and_name=lookup)
    actor = ActorContext(tenant_id=1, user_id=123, user_role="member")

    expected_df = pd.DataFrame([{"id": 1}, {"id": 2}])
    fake_manager = _patch_query_execution(monkeypatch, service, expected_df)

    df = await service.query_data_for_actor(
        data_source_id=1,
        sql_query="SELECT * FROM orders",
        actor=actor,
        params={"foo": "bar"},
    )

    assert len(df) == 2
    assert fake_manager.calls == [("SELECT * FROM orders", {"foo": "bar"})]


@pytest.mark.asyncio
async def test_query_data_resolves_schema_qualified_ref_to_registered_asset_name(monkeypatch):
    registered = SimpleNamespace(id=11, asset_name="orders")
    service = _service_with_asset_lookup(get_by_data_source_and_name=AsyncMock(return_value=registered))
    actor = ActorContext(tenant_id=1, user_id=123, user_role="member")
    fake_manager = _patch_query_execution(monkeypatch, service, pd.DataFrame([{"id": 1}]))

    await service.query_data_for_actor(
        data_source_id=1,
        sql_query="SELECT * FROM main.gold.orders",
        actor=actor,
    )

    assert fake_manager.calls == [("SELECT * FROM main.gold.orders", None)]


@pytest.mark.asyncio
async def test_query_data_ignores_cte_alias_for_asset_whitelist(monkeypatch):
    registered = SimpleNamespace(id=11, asset_name="orders")
    lookup = AsyncMock(return_value=registered)
    service = _service_with_asset_lookup(get_by_data_source_and_name=lookup)
    actor = ActorContext(tenant_id=1, user_id=123, user_role="member")
    fake_manager = _patch_query_execution(monkeypatch, service, pd.DataFrame([{"id": 1}]))

    await service.query_data_for_actor(
        data_source_id=1,
        sql_query="WITH scoped AS (SELECT * FROM orders) SELECT * FROM scoped",
        actor=actor,
    )

    assert len(fake_manager.calls) == 1


@pytest.mark.asyncio
async def test_query_data_denies_information_schema_when_only_business_asset_registered(monkeypatch):
    registered = SimpleNamespace(id=11, asset_name="orders")

    async def _lookup(_ds_id: int, name: str):
        return registered if name == "orders" else None

    lookup = AsyncMock(side_effect=_lookup)
    service = _service_with_asset_lookup(get_by_data_source_and_name=lookup)
    actor = ActorContext(tenant_id=1, user_id=123, user_role="member")
    _patch_query_execution(monkeypatch, service, pd.DataFrame([{"id": 1}]))

    sql = (
        "SELECT table_schema, table_name FROM information_schema.tables "
        "WHERE table_schema NOT IN ('pg_catalog', 'information_schema')"
    )
    with pytest.raises(AuthorizationError, match="information_schema.tables"):
        await service.query_data_for_actor(data_source_id=1, sql_query=sql, actor=actor)


@pytest.mark.asyncio
async def test_query_data_tables_asset_does_not_authorize_information_schema(monkeypatch):
    tables_asset = SimpleNamespace(id=12, asset_name="tables")

    async def _lookup(_ds_id: int, name: str):
        return tables_asset if name == "tables" else None

    service = _service_with_asset_lookup(get_by_data_source_and_name=AsyncMock(side_effect=_lookup))
    actor = ActorContext(tenant_id=1, user_id=123, user_role="member")
    _patch_query_execution(monkeypatch, service, pd.DataFrame([{"id": 1}]))

    with pytest.raises(AuthorizationError, match="information_schema.tables"):
        await service.query_data_for_actor(
            data_source_id=1,
            sql_query="SELECT * FROM information_schema.tables",
            actor=actor,
        )


@pytest.mark.asyncio
async def test_query_data_applies_max_rows_limit(monkeypatch):
    service = _service_with_asset_lookup()
    actor = ActorContext(tenant_id=1, user_id=123, user_role="member")

    expected_df = pd.DataFrame([{"id": 1}, {"id": 2}, {"id": 3}])
    fake_manager = _patch_query_execution(monkeypatch, service, expected_df)

    df = await service.query_data_for_actor(
        data_source_id=1,
        sql_query="SELECT 1",
        actor=actor,
        max_rows=2,
    )

    assert len(df) == 2
