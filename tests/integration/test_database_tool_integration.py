"""Integration tests for database agent tools.

These tests execute tools through the same execution path as the agent
(direct tool invocation with RunnableConfig), without HTTP.
"""

import json

import pandas as pd
import pytest

from apps.shared.data_source.service import DataSourceService
from apps.shared.db.models import AssetMetadata, DataSource, Tenant
from apps.tenant_app_service.agents.tools import database as database_tool


class _SessionContext:
    """Simple async context manager that reuses a provided session."""

    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeDBManager:
    def __init__(self, df: pd.DataFrame):
        self._df = df

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def query(self, sql: str, params: dict | None = None) -> pd.DataFrame:
        return self._df


async def _seed_tenant(async_db_session, runtime_context) -> Tenant:
    from apps.shared.db.models import User

    tenant = Tenant(id=runtime_context.tenant.tenant_id, name=runtime_context.tenant.tenant_name)
    async_db_session.add(tenant)
    await async_db_session.flush()
    user = User(
        id=runtime_context.user.user_id,
        username=runtime_context.user.username,
        email=f"{runtime_context.user.username}@example.com",
        hashed_password="hashed",
        role=runtime_context.user.role,
        tenant_id=runtime_context.user.tenant_id,
    )
    async_db_session.add(user)
    await async_db_session.commit()
    return tenant


async def _seed_data_source(async_db_session, runtime_context) -> DataSource:
    data_source = DataSource(
        tenant_id=runtime_context.tenant.tenant_id,
        owner_id=runtime_context.user.user_id,
        name="test_datasource",
        type="postgres",
        managed=False,
        config={
            "host": "localhost",
            "port": 5432,
            "database": "analytics",
            "username": "user",
            "password": "password",
        },
        description="Test data source",
    )
    async_db_session.add(data_source)
    await async_db_session.commit()
    await async_db_session.refresh(data_source)
    return data_source


async def _seed_asset(async_db_session, data_source_id: int, owner_id: int) -> AssetMetadata:
    asset = AssetMetadata(
        data_source_id=data_source_id,
        owner_id=owner_id,
        asset_name="orders",
        asset_type="table",
        columns=[],
        row_count=10,
        source_info={},
    )
    async_db_session.add(asset)
    await async_db_session.commit()
    await async_db_session.refresh(asset)
    return asset


@pytest.mark.asyncio
async def test_list_data_sources_tool_returns_dialect_hints(
    async_db_session,
    runtime_context,
    runnable_config,
    monkeypatch,
):
    monkeypatch.setattr(
        database_tool,
        "app_db_session",
        lambda: _SessionContext(async_db_session),
    )

    await _seed_tenant(async_db_session, runtime_context)
    data_source = await _seed_data_source(async_db_session, runtime_context)

    result = await database_tool.list_data_sources.ainvoke({}, config=runnable_config)
    payload = json.loads(result.content)

    assert len(payload) == 1
    assert payload[0]["data_source_id"] == data_source.id
    assert payload[0]["name"] == data_source.name
    assert payload[0]["type"] == data_source.type
    assert "SQL Dialect Hints" in payload[0]["description"]


@pytest.mark.asyncio
async def test_run_sql_query_on_datasource_formats_rows_and_truncates_cells(
    async_db_session,
    runtime_context,
    runnable_config,
    monkeypatch,
):
    monkeypatch.setattr(
        database_tool,
        "app_db_session",
        lambda: _SessionContext(async_db_session),
    )

    await _seed_tenant(async_db_session, runtime_context)
    data_source = await _seed_data_source(async_db_session, runtime_context)
    await _seed_asset(async_db_session, data_source.id, runtime_context.user.user_id)

    long_text = "x" * (database_tool.MAX_CELL_LENGTH + 10)
    df = pd.DataFrame(
        [
            {"id": 1, "note": long_text},
            {"id": 2, "note": "short"},
        ]
    )

    async def _fake_get_db_manager(self, data_source_id: int):
        return _FakeDBManager(df)

    monkeypatch.setattr(DataSourceService, "get_db_manager", _fake_get_db_manager)

    result = await database_tool.run_sql_query_on_datasource.ainvoke(
        {
            "data_source_id": data_source.id,
            "sql_query": "SELECT * FROM orders",
        },
        config=runnable_config,
    )
    payload = json.loads(result.content)

    assert payload["row_count"] == 2
    assert payload["columns"] == ["id", "note"]
    assert payload["rows"][0]["note"].endswith("...[truncated]")


@pytest.mark.asyncio
async def test_run_sql_query_on_datasource_caps_row_limit(
    async_db_session,
    runtime_context,
    runnable_config,
    monkeypatch,
):
    monkeypatch.setattr(
        database_tool,
        "app_db_session",
        lambda: _SessionContext(async_db_session),
    )

    await _seed_tenant(async_db_session, runtime_context)
    data_source = await _seed_data_source(async_db_session, runtime_context)
    await _seed_asset(async_db_session, data_source.id, runtime_context.user.user_id)

    large_asset = AssetMetadata(
        data_source_id=data_source.id,
        owner_id=runtime_context.user.user_id,
        asset_name="large_table",
        asset_type="table",
        columns=[],
        row_count=database_tool.MAX_QUERY_RESULT_ROWS + 1,
        source_info={},
    )
    async_db_session.add(large_asset)
    await async_db_session.commit()

    df = pd.DataFrame([{"value": i} for i in range(database_tool.MAX_QUERY_RESULT_ROWS + 1)])

    async def _fake_get_db_manager(self, data_source_id: int):
        return _FakeDBManager(df)

    monkeypatch.setattr(DataSourceService, "get_db_manager", _fake_get_db_manager)

    result = await database_tool.run_sql_query_on_datasource.ainvoke(
        {
            "data_source_id": data_source.id,
            "sql_query": "SELECT * FROM large_table",
        },
        config=runnable_config,
    )
    payload = json.loads(result.content)

    assert "error" not in payload
    assert payload["row_count"] == database_tool.MAX_QUERY_RESULT_ROWS
    assert len(payload["rows"]) == database_tool.MAX_QUERY_RESULT_ROWS
