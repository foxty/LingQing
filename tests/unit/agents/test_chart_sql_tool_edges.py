"""Edge cases for create_chart_from_sql."""

from unittest.mock import AsyncMock

import pandas as pd
import pytest
from langchain_core.runnables import RunnableConfig

from apps.shared.chart.types import ChartRenderResult
from apps.tenant_app_service.agents.domain import AgentCapabilityProfile
from apps.tenant_app_service.agents.tools.chart import create_chart_from_sql
from apps.tenant_app_service.agents.tools.tool_result import ToolResultStatus

PNG = b"\x89PNG\r\n\x1a\n"


class _FakeSessionContext:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.mark.asyncio
async def test_create_chart_from_sql_empty_result(monkeypatch, runnable_config):
    class _FakeService:
        def __init__(self, tenant_id, data_source_repo, asset_repo):
            pass

        async def query_data_for_actor(self, **kwargs):
            return pd.DataFrame()

    monkeypatch.setattr("apps.tenant_app_service.agents.tools.chart_support.app_db_session", lambda: _FakeSessionContext())
    monkeypatch.setattr("apps.tenant_app_service.agents.tools.chart_support.DataSourceService", _FakeService)

    result = await create_chart_from_sql.ainvoke(
        {
            "data_source_id": 3,
            "sql_query": "SELECT 1 WHERE 1=0",
            "chart_type": "bar",
            "x_key": "x",
            "y_key": "y",
            "title": "Empty",
        },
        config=runnable_config,
    )

    assert result.status == ToolResultStatus.ERROR
    assert result.error is not None
    assert result.error.code == "CHART_SQL_EMPTY_RESULT"


@pytest.mark.asyncio
async def test_create_chart_from_sql_permission_denied(monkeypatch, runnable_config):
    runtime = dict(runnable_config["configurable"]["runtime"])
    runtime["capability_profile"] = AgentCapabilityProfile(allowed_data_source_ids=[1, 2]).model_dump()
    config = RunnableConfig(configurable={**runnable_config["configurable"], "runtime": runtime})

    result = await create_chart_from_sql.ainvoke(
        {
            "data_source_id": 99,
            "sql_query": "SELECT 1",
            "chart_type": "bar",
            "x_key": "x",
            "y_key": "y",
            "title": "Denied",
        },
        config=config,
    )

    assert result.status == ToolResultStatus.ERROR
    assert result.error is not None
    assert result.error.code == "PERMISSION_DENIED"


@pytest.mark.asyncio
async def test_create_chart_from_sql_truncates_to_500_rows(monkeypatch, runnable_config):
    class _FakeService:
        def __init__(self, tenant_id, data_source_repo, asset_repo):
            pass

        async def query_data_for_actor(self, **kwargs):
            return pd.DataFrame([{"x": f"p{i}", "y": i} for i in range(600)])

    render_rows: dict = {}

    def _fake_render_chart(**kwargs):
        import json

        render_rows["count"] = len(json.loads(kwargs["data"]))
        return ChartRenderResult(svg_bytes=b"<svg/>", png_bytes=PNG, title=kwargs.get("title", "Chart"))

    monkeypatch.setattr("apps.tenant_app_service.agents.tools.chart_support.app_db_session", lambda: _FakeSessionContext())
    monkeypatch.setattr("apps.tenant_app_service.agents.tools.chart_support.DataSourceService", _FakeService)
    monkeypatch.setattr("apps.tenant_app_service.agents.tools.chart.render_chart", _fake_render_chart)
    monkeypatch.setattr(
        "apps.tenant_app_service.agents.tools.chart.register_agent_chart",
        AsyncMock(return_value="![T](/charts/1/image.svg)"),
    )

    result = await create_chart_from_sql.ainvoke(
        {
            "data_source_id": 3,
            "sql_query": "SELECT x, y FROM big",
            "chart_type": "line",
            "x_key": "x",
            "y_key": "y",
            "title": "Big",
        },
        config=runnable_config,
    )

    assert result.status == ToolResultStatus.SUCCESS
    assert render_rows["count"] == 500


@pytest.mark.asyncio
async def test_create_chart_from_sql_surfaces_query_error_detail(monkeypatch, runnable_config):
    class _FakeService:
        def __init__(self, tenant_id, data_source_repo, asset_repo):
            pass

        async def query_data_for_actor(self, **kwargs):
            raise ConnectionError("Query execution failed: syntax error near 'FROM'")

    monkeypatch.setattr("apps.tenant_app_service.agents.tools.chart_support.app_db_session", lambda: _FakeSessionContext())
    monkeypatch.setattr("apps.tenant_app_service.agents.tools.chart_support.DataSourceService", _FakeService)

    result = await create_chart_from_sql.ainvoke(
        {
            "data_source_id": 3,
            "sql_query": "SELECT FROM broken",
            "chart_type": "bar",
            "x_key": "x",
            "y_key": "y",
            "title": "Bad SQL",
        },
        config=runnable_config,
    )

    assert result.status == ToolResultStatus.ERROR
    assert result.error is not None
    assert "syntax error" in result.error.message
    assert result.error.hint is not None
