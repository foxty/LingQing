"""Unit tests for multi-panel chart grid agent tools."""

import json

import pandas as pd
import pytest

from apps.shared.chart.types import ChartRenderResult
from apps.tenant_app_service.agents.tools.chart_grid import (
    create_chart_grid_from_sql,
    create_chart_grid_from_structured_data,
)
from apps.tenant_app_service.agents.tools.tool_result import ToolResultStatus

PNG = b"\x89PNG\r\n\x1a\n"


@pytest.mark.asyncio
async def test_create_chart_grid_from_structured_data_registers_chart(monkeypatch, runnable_config):
    render_calls: list[dict] = []

    def _fake_render_chart_grid(**kwargs):
        render_calls.append(kwargs)
        return ChartRenderResult(svg_bytes=b"<svg/>", png_bytes=PNG, title=kwargs["title"])

    monkeypatch.setattr(
        "apps.tenant_app_service.agents.tools.chart_grid.render_chart_grid",
        _fake_render_chart_grid,
    )

    async def _fake_register(**kwargs):
        return "\n\n![Grid](http://127.0.0.1:8000/charts/9/image.svg)\n\n"

    monkeypatch.setattr("apps.tenant_app_service.agents.tools.chart_grid.register_agent_chart", _fake_register)

    panels = json.dumps([{"chart_type": "bar", "x_key": "m", "y_key": "a", "row": 1, "col": 1}])
    result = await create_chart_grid_from_structured_data.ainvoke(
        {
            "data": '[{"m":"Jan","a":1}]',
            "title": "Overview",
            "panels": panels,
            "rows": 1,
            "cols": 1,
            "subtitle": "FY2026",
        },
        config=runnable_config,
    )

    assert result.status == ToolResultStatus.SUCCESS
    assert "/charts/9/image.svg" in result.content
    assert render_calls[0]["subtitle"] == "FY2026"
    assert render_calls[0]["rows"] == 1


@pytest.mark.asyncio
async def test_create_chart_grid_from_structured_data_validation_error(runnable_config):
    result = await create_chart_grid_from_structured_data.ainvoke(
        {
            "data": '[{"m":"Jan","a":1}]',
            "title": "Bad",
            "panels": "[]",
        },
        config=runnable_config,
    )
    assert result.status == ToolResultStatus.ERROR
    assert result.error.code == "CHART_GRID_VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_create_chart_grid_from_sql_uses_query_data(monkeypatch, runnable_config):
    class _FakeSessionContext:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    captured: dict = {}

    class _FakeService:
        def __init__(self, tenant_id, data_source_repo, asset_repo):
            captured["tenant_id"] = tenant_id

        async def query_data_for_actor(self, **kwargs):
            captured["query_kwargs"] = kwargs
            return pd.DataFrame([{"month": "Jan", "sales": 10}])

    monkeypatch.setattr("apps.tenant_app_service.agents.tools.chart_support.app_db_session", lambda: _FakeSessionContext())
    monkeypatch.setattr("apps.tenant_app_service.agents.tools.chart_support.DataSourceService", _FakeService)

    render_calls: list[dict] = []

    def _fake_render_chart_grid(**kwargs):
        render_calls.append(kwargs)
        return ChartRenderResult(svg_bytes=b"<svg/>", png_bytes=PNG, title=kwargs["title"])

    monkeypatch.setattr(
        "apps.tenant_app_service.agents.tools.chart_grid.render_chart_grid",
        _fake_render_chart_grid,
    )

    async def _fake_register(**kwargs):
        return "\n\n![Grid](http://127.0.0.1:8000/charts/3/image.svg)\n\n"

    monkeypatch.setattr("apps.tenant_app_service.agents.tools.chart_grid.register_agent_chart", _fake_register)

    panels = json.dumps([{"chart_type": "line", "x_key": "month", "y_key": "sales", "row": 1, "col": 1}])
    result = await create_chart_grid_from_sql.ainvoke(
        {
            "data_source_id": 2,
            "sql_query": "SELECT month, sales FROM t",
            "title": "SQL Grid",
            "panels": panels,
        },
        config=runnable_config,
    )

    assert result.status == ToolResultStatus.SUCCESS
    assert captured["tenant_id"] == 1
    assert render_calls[0]["title"] == "SQL Grid"
    loaded = json.loads(render_calls[0]["data"])
    assert loaded == [{"month": "Jan", "sales": 10}]
