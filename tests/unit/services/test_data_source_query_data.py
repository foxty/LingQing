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


@pytest.mark.asyncio
async def test_query_data_rejects_non_select_sql():
    service = DataSourceService(
        tenant_id=1,
        data_source_repo=SimpleNamespace(),
        asset_repo=SimpleNamespace(db=object()),
    )
    actor = ActorContext(tenant_id=1, user_id=1, user_role="member")

    with pytest.raises(ValidationError, match="read-only SELECT"):
        await service.query_data_for_actor(data_source_id=1, sql_query="UPDATE orders SET amount = 1", actor=actor)


@pytest.mark.asyncio
async def test_query_data_denies_when_data_source_read_denied(monkeypatch):
    service = DataSourceService(
        tenant_id=1,
        data_source_repo=SimpleNamespace(),
        asset_repo=SimpleNamespace(db=object()),
    )
    actor = ActorContext(tenant_id=1, user_id=123, user_role="member")

    monkeypatch.setattr(
        service,
        "require_read_access_for_actor",
        AsyncMock(side_effect=AuthorizationError("无权访问该数据源")),
    )

    with pytest.raises(AuthorizationError, match="无权访问该数据源"):
        await service.query_data_for_actor(data_source_id=1, sql_query="SELECT * FROM orders", actor=actor)


@pytest.mark.asyncio
async def test_query_data_allows_and_executes_when_data_source_access_passes(monkeypatch):
    service = DataSourceService(
        tenant_id=1,
        data_source_repo=SimpleNamespace(),
        asset_repo=SimpleNamespace(db=object()),
    )
    actor = ActorContext(tenant_id=1, user_id=123, user_role="member")

    expected_df = pd.DataFrame([{"id": 1}, {"id": 2}])
    fake_manager = _FakeDBManager(expected_df)
    monkeypatch.setattr(service, "get_db_manager", AsyncMock(return_value=fake_manager))
    monkeypatch.setattr(service, "require_read_access_for_actor", AsyncMock(return_value=SimpleNamespace()))

    df = await service.query_data_for_actor(
        data_source_id=1,
        sql_query="SELECT * FROM orders",
        actor=actor,
        params={"foo": "bar"},
    )

    assert len(df) == 2
    assert fake_manager.calls == [("SELECT * FROM orders", {"foo": "bar"})]


@pytest.mark.asyncio
async def test_query_data_applies_max_rows_limit(monkeypatch):
    service = DataSourceService(
        tenant_id=1,
        data_source_repo=SimpleNamespace(),
        asset_repo=SimpleNamespace(db=object()),
    )
    actor = ActorContext(tenant_id=1, user_id=123, user_role="member")

    expected_df = pd.DataFrame([{"id": 1}, {"id": 2}, {"id": 3}])
    fake_manager = _FakeDBManager(expected_df)
    monkeypatch.setattr(service, "get_db_manager", AsyncMock(return_value=fake_manager))
    monkeypatch.setattr(service, "require_read_access_for_actor", AsyncMock(return_value=SimpleNamespace()))

    df = await service.query_data_for_actor(
        data_source_id=1,
        sql_query="SELECT 1",
        actor=actor,
        max_rows=2,
    )

    assert len(df) == 2
