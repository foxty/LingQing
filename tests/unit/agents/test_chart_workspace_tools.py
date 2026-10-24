"""Unit tests for chart/workspace SQL tools using auth-aware DataSourceService.query_data_for_actor."""

import json

import pandas as pd
import pytest

from apps.shared.chart.types import ChartRenderResult
from apps.tenant_app_service.agents.tools.chart import create_chart_from_sql, create_chart_from_structured_data
from apps.tenant_app_service.agents.tools.tool_result import ToolResultStatus
from apps.tenant_app_service.agents.tools.workspace import create_materialized_view, join_cross_datasource

PNG = b"\x89PNG\r\n\x1a\n"


@pytest.mark.asyncio
async def test_create_chart_from_structured_data_injects_runtime_config(monkeypatch, runnable_config):
    render_kwargs: dict = {}

    def _fake_render_chart(**kwargs):
        render_kwargs.update(kwargs)
        return ChartRenderResult(svg_bytes=b"<svg/>", png_bytes=PNG, title=kwargs.get("title", "Chart"))

    monkeypatch.setattr("apps.tenant_app_service.agents.tools.chart.render_chart", _fake_render_chart)

    async def _fake_register(**kwargs):
        return "\n\n![Monthly](http://127.0.0.1:8000/charts/2/image.svg)\n\n"

    monkeypatch.setattr("apps.tenant_app_service.agents.tools.chart.register_agent_chart", _fake_register)

    result = await create_chart_from_structured_data.ainvoke(
        {
            "chart_type": "bar",
            "data": '[{"month":"Jan","sales":100}]',
            "title": "Monthly",
            "x_key": "month",
            "y_key": "sales",
        },
        config=runnable_config,
    )

    assert result.status == ToolResultStatus.SUCCESS
    assert "/charts/2/image.svg" in result.content
    assert "/charts/2/image.svg" in result.metadata["raw_result"]["markdown"]
    assert render_kwargs["title"] == "Monthly"


@pytest.mark.asyncio
async def test_create_chart_from_structured_data_forwards_enhancement_kwargs(monkeypatch, runnable_config):
    render_kwargs: dict = {}

    def _fake_render_chart(**kwargs):
        render_kwargs.update(kwargs)
        return ChartRenderResult(svg_bytes=b"<svg/>", png_bytes=PNG, title=kwargs.get("title", "Chart"))

    monkeypatch.setattr("apps.tenant_app_service.agents.tools.chart.render_chart", _fake_render_chart)

    async def _fake_register(**kwargs):
        return "\n\n![Chart](http://127.0.0.1:8000/charts/5/image.svg)\n\n"

    monkeypatch.setattr("apps.tenant_app_service.agents.tools.chart.register_agent_chart", _fake_register)

    await create_chart_from_structured_data.ainvoke(
        {
            "chart_type": "waterfall",
            "data": '[{"step":"A","amount":1}]',
            "title": "Bridge",
            "x_key": "step",
            "y_key": "amount",
            "subtitle": "FY2026",
            "reference_lines_json": '[{"y": 0.5}]',
            "annotations_json": '[{"text": "note"}]',
            "y_axis_percent": True,
            "measure_key": "kind",
        },
        config=runnable_config,
    )

    assert render_kwargs["subtitle"] == "FY2026"
    assert render_kwargs["reference_lines_json"] == '[{"y": 0.5}]'
    assert render_kwargs["annotations_json"] == '[{"text": "note"}]'
    assert render_kwargs["y_axis_percent"] is True
    assert render_kwargs["measure_key"] == "kind"


@pytest.mark.asyncio
async def test_create_chart_from_structured_data_schema_hides_config():
    assert "config" not in create_chart_from_structured_data.args_schema.model_fields


def test_create_chart_from_structured_data_schema_chart_type_enum():
    schema = create_chart_from_structured_data.args_schema.model_json_schema()
    chart_type_schema = schema["properties"]["chart_type"]
    assert set(chart_type_schema["enum"]) == {
        "bar",
        "horizontal_bar",
        "line",
        "area",
        "pie",
        "scatter",
        "heatmap",
        "waterfall",
        "box",
        "violin",
    }


@pytest.mark.asyncio
async def test_create_chart_from_sql_uses_query_data(monkeypatch, runnable_config):
    class _FakeSessionContext:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    captured = {}

    class _FakeService:
        def __init__(self, tenant_id, data_source_repo, asset_repo):
            captured["tenant_id"] = tenant_id

        async def query_data_for_actor(self, **kwargs):
            captured["query_kwargs"] = kwargs
            return pd.DataFrame([{"month": "Jan", "total": 10}])

    monkeypatch.setattr("apps.tenant_app_service.agents.tools.chart_support.app_db_session", lambda: _FakeSessionContext())
    monkeypatch.setattr("apps.tenant_app_service.agents.tools.chart_support.DataSourceService", _FakeService)

    render_kwargs: dict = {}

    def _fake_render_chart(**kwargs):
        render_kwargs.update(kwargs)
        return ChartRenderResult(svg_bytes=b"<svg/>", png_bytes=PNG, title=kwargs.get("title", "Chart"))

    monkeypatch.setattr("apps.tenant_app_service.agents.tools.chart.render_chart", _fake_render_chart)

    async def _fake_register(**kwargs):
        return "\n\n![Monthly](http://127.0.0.1:8000/charts/1/image.svg)\n\n"

    monkeypatch.setattr("apps.tenant_app_service.agents.tools.chart.register_agent_chart", _fake_register)

    result = await create_chart_from_sql.ainvoke(
        {
            "data_source_id": 3,
            "sql_query": "SELECT month, total FROM sales",
            "chart_type": "line",
            "x_key": "month",
            "y_key": "total",
            "title": "Monthly",
        },
        config=runnable_config,
    )

    assert result.status == ToolResultStatus.SUCCESS
    assert "/charts/1/image.svg" in result.content
    assert captured["tenant_id"] == 1
    assert captured["query_kwargs"]["data_source_id"] == 3
    assert captured["query_kwargs"]["actor"].user_id == 123
    assert captured["query_kwargs"]["actor"].user_role == "admin"
    assert render_kwargs["title"] == "Monthly"


@pytest.mark.asyncio
async def test_create_materialized_view_uses_query_data_and_writes(monkeypatch, runnable_config):
    class _FakeSessionContext:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class _FakeDBManager:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def insert_dataframe(self, table_name, df, if_exists="replace"):
            assert table_name == "_temp_x"
            assert if_exists == "replace"
            assert len(df) == 1

    class _FakeService:
        def __init__(self, tenant_id, data_source_repo, asset_repo):
            self.tenant_id = tenant_id

        async def get_data_source_for_actor(self, *, data_source_id, actor, **kwargs):
            return type("DS", (), {"name": "managed_ds", "managed": True})()

        async def query_data_for_actor(self, **kwargs):
            return pd.DataFrame([{"id": 1}])

        async def get_db_manager(self, data_source_id):
            return _FakeDBManager()

    async def _fake_register_temp_table(**kwargs):
        return None

    monkeypatch.setattr("apps.tenant_app_service.agents.tools.workspace.app_db_session", lambda: _FakeSessionContext())
    monkeypatch.setattr("apps.tenant_app_service.agents.tools.workspace.DataSourceService", _FakeService)
    monkeypatch.setattr(
        "apps.tenant_app_service.agents.tools.workspace.generate_temp_table_name",
        lambda thread_id, view_name: "_temp_x",
    )
    monkeypatch.setattr("apps.tenant_app_service.agents.tools.workspace.register_temp_table", _fake_register_temp_table)

    result = await create_materialized_view.ainvoke(
        {
            "data_source_id": 5,
            "sql_query": "SELECT * FROM orders",
            "view_name": "orders_mv",
        },
        config=runnable_config,
    )

    payload = json.loads(result.content)

    assert result.status == ToolResultStatus.SUCCESS
    assert payload["status"] == "success"
    assert payload["view_name"] == "_temp_x"
    assert payload["row_count"] == 1


@pytest.mark.asyncio
async def test_join_cross_datasource_uses_query_data_for_both_sides(monkeypatch, runnable_config):
    class _FakeSessionContext:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    calls = []

    class _FakeDBManager:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def insert_dataframe(self, table_name, df, if_exists="replace"):
            assert if_exists == "replace"

    class _FakeService:
        def __init__(self, tenant_id, data_source_repo, asset_repo):
            pass

        async def get_data_source_for_actor(self, *, data_source_id, actor, **kwargs):
            return type("DS", (), {"name": f"ds_{data_source_id}", "managed": False})()

        async def query_data_for_actor(self, **kwargs):
            calls.append(kwargs)
            if kwargs["data_source_id"] == 1:
                return pd.DataFrame([{"customer_id": 1, "revenue": 10}])
            return pd.DataFrame([{"id": 1, "name": "Acme"}])

        async def get_db_manager(self, data_source_id):
            return _FakeDBManager()

    async def _fake_get_managed_datasource(tenant_id, session):
        return type("DS", (), {"id": 99, "name": "workspace", "managed": True})()

    async def _fake_register_temp_table(**kwargs):
        return None

    monkeypatch.setattr("apps.tenant_app_service.agents.tools.workspace.app_db_session", lambda: _FakeSessionContext())
    monkeypatch.setattr("apps.tenant_app_service.agents.tools.workspace.DataSourceService", _FakeService)
    monkeypatch.setattr(
        "apps.tenant_app_service.agents.tools.workspace.get_managed_datasource", _fake_get_managed_datasource
    )
    monkeypatch.setattr("apps.tenant_app_service.agents.tools.workspace.register_temp_table", _fake_register_temp_table)
    monkeypatch.setattr(
        "apps.tenant_app_service.agents.tools.workspace.generate_temp_table_name",
        lambda thread_id, result_name: "_temp_join",
    )

    result = await join_cross_datasource.ainvoke(
        {
            "left_data_source_id": 1,
            "left_query": "SELECT customer_id, revenue FROM l",
            "right_data_source_id": 2,
            "right_query": "SELECT id, name FROM r",
            "join_type": "left",
            "left_on": "customer_id",
            "right_on": "id",
            "result_name": "joined",
        },
        config=runnable_config,
    )
    payload = json.loads(result.content)

    assert result.status == ToolResultStatus.SUCCESS
    assert payload["status"] == "success"
    assert payload["temp_table_name"] == "_temp_join"
    assert len(calls) == 2
    assert {call["data_source_id"] for call in calls} == {1, 2}
    assert all(call["actor"].user_id == 123 for call in calls)
    assert all(call["actor"].user_role == "admin" for call in calls)
