"""Integration tests for dashboard agent tools.

These tests execute tools through the same execution path as the agent
(direct tool invocation with RunnableConfig), without HTTP.
"""

import json

import pytest
from sqlalchemy import select

from apps.shared.core.exceptions import AuthorizationError, ValidationError
from apps.shared.db.models import AclGrant as AclGrantModel
from apps.shared.db.models import Agent, Artifact, ArtifactLink, ChatThread, Dashboard, Tenant, User
from apps.tenant_app_service.agents.tools import dashboard_base, dashboard_filter, dashboard_widget
from apps.tenant_app_service.agents.tools.tool_result import ToolResultStatus
from tests.integration.tool_integration_helpers import build_runnable_config_for_actor


class _SessionContext:
    """Simple async context manager that reuses a provided session."""

    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, exc_type, exc, tb):
        return False


async def _seed_base_records(async_db_session, runtime_context) -> None:
    tenant = Tenant(id=runtime_context.tenant.tenant_id, name=runtime_context.tenant.tenant_name)
    user = User(
        id=runtime_context.user.user_id,
        username=runtime_context.user.username,
        email=f"{runtime_context.user.username}@example.com",
        hashed_password="test_password_hash",
        role=runtime_context.user.role,
        tenant_id=runtime_context.user.tenant_id,
    )
    agent = Agent(
        id=runtime_context.agent_id,
        tenant_id=runtime_context.tenant.tenant_id,
        owner_id=runtime_context.user.user_id,
        name=runtime_context.agent_name,
        description="test agent",
        system_prompt="You are a test agent.",
        config={},
        tags=None,
        example_questions=None,
    )
    thread = ChatThread(
        id=runtime_context.thread_id,
        tenant_id=runtime_context.tenant.tenant_id,
        user_id=runtime_context.user.user_id,
        agent_id=runtime_context.agent_id,
        title="test thread",
    )
    async_db_session.add_all([tenant, user])
    await async_db_session.flush()
    async_db_session.add(agent)
    await async_db_session.flush()
    async_db_session.add(thread)
    await async_db_session.commit()


async def _create_dashboard(async_db_session, runnable_config) -> dict:
    result = await dashboard_base.create_dashboard.ainvoke(
        {
            "title": "Sales Dashboard",
            "description": "Integration test dashboard",
        },
        config=runnable_config,
    )
    return json.loads(result.content)


@pytest.mark.asyncio
async def test_creates_dashboard_and_artifact_link(
    async_db_session,
    runtime_context,
    runnable_config,
    monkeypatch,
):
    """Proof-of-concept integration test for create_dashboard tool."""
    # Patch app_db_session to reuse the async_db_session fixture
    monkeypatch.setattr(
        dashboard_base,
        "app_db_session",
        lambda: _SessionContext(async_db_session),
    )

    # Arrange: create tenant/user/agent/thread records matching runtime_context
    await _seed_base_records(async_db_session, runtime_context)

    # Act: execute tool with runnable config
    result = await _create_dashboard(async_db_session, runnable_config)

    assert "dashboard_id" in result
    assert result["preview_url"].endswith(f"/dashboards/{result['dashboard_id']}/embed")

    # Assert: dashboard + artifact/link are persisted
    dashboard = await async_db_session.get(Dashboard, result["dashboard_id"])
    assert dashboard is not None
    assert dashboard.tenant_id == runtime_context.tenant.tenant_id

    stmt = select(Artifact).where(
        Artifact.artifact_type == "dashboard",
        Artifact.resource_id == dashboard.id,
        Artifact.tenant_id == runtime_context.tenant.tenant_id,
    )
    artifact = (await async_db_session.execute(stmt)).scalar_one_or_none()
    assert artifact is not None

    link_stmt = select(ArtifactLink).where(
        ArtifactLink.artifact_id == artifact.id,
        ArtifactLink.thread_id == runtime_context.thread_id,
    )
    link = (await async_db_session.execute(link_stmt)).scalar_one_or_none()
    assert link is not None


@pytest.mark.asyncio
async def test_get_dashboard_config_includes_layout_and_widget_order(
    async_db_session,
    runtime_context,
    runnable_config,
    monkeypatch,
):
    monkeypatch.setattr(
        dashboard_base,
        "app_db_session",
        lambda: _SessionContext(async_db_session),
    )
    monkeypatch.setattr(
        dashboard_widget,
        "app_db_session",
        lambda: _SessionContext(async_db_session),
    )
    await _seed_base_records(async_db_session, runtime_context)

    dashboard_result = await _create_dashboard(async_db_session, runnable_config)
    dashboard_id = dashboard_result["dashboard_id"]

    await dashboard_widget.add_widget_to_dashboard.ainvoke(
        {
            "dashboard_id": dashboard_id,
            "widget_data": {
                "widget_type": "metric",
            },
        },
        config=runnable_config,
    )

    config_result = await dashboard_base.get_dashboard_config.ainvoke(
        {"dashboard_id": dashboard_id},
        config=runnable_config,
    )
    config = json.loads(config_result.content)

    assert config["dashboard_id"] == dashboard_id
    assert config["config"]["layout"]["cols"] == 12
    assert config["config"]["widgets"][0]["_order"] == 1


@pytest.mark.asyncio
async def test_add_update_remove_widget_flow(
    async_db_session,
    runtime_context,
    runnable_config,
    monkeypatch,
):
    monkeypatch.setattr(
        dashboard_base,
        "app_db_session",
        lambda: _SessionContext(async_db_session),
    )
    monkeypatch.setattr(
        dashboard_widget,
        "app_db_session",
        lambda: _SessionContext(async_db_session),
    )
    await _seed_base_records(async_db_session, runtime_context)

    dashboard_result = await _create_dashboard(async_db_session, runnable_config)
    dashboard_id = dashboard_result["dashboard_id"]

    add_result = await dashboard_widget.add_widget_to_dashboard.ainvoke(
        {
            "dashboard_id": dashboard_id,
            "widget_data": {
                "widget_type": "metric",
            },
        },
        config=runnable_config,
    )
    add_payload = json.loads(add_result.content)
    widget_id = add_payload["id"]

    update_result = await dashboard_widget.update_widget.ainvoke(
        {
            "dashboard_id": dashboard_id,
            "widget_id": widget_id,
            "position": {"x": 0, "y": 0, "w": 6, "h": 4},
        },
        config=runnable_config,
    )
    update_payload = json.loads(update_result.content)
    assert update_payload["position"]["w"] == 6

    remove_result = await dashboard_widget.remove_widget.ainvoke(
        {"dashboard_id": dashboard_id, "widget_id": widget_id},
        config=runnable_config,
    )
    remove_payload = json.loads(remove_result.content)
    assert remove_payload["id"] == widget_id
    assert remove_payload["deleted"] is True

    config_result = await dashboard_base.get_dashboard_config.ainvoke(
        {"dashboard_id": dashboard_id},
        config=runnable_config,
    )
    config = json.loads(config_result.content)
    assert config["config"]["widgets"] == []


@pytest.mark.asyncio
async def test_update_dashboard_layout_updates_config_layout(
    async_db_session,
    runtime_context,
    runnable_config,
    monkeypatch,
):
    monkeypatch.setattr(
        dashboard_base,
        "app_db_session",
        lambda: _SessionContext(async_db_session),
    )
    await _seed_base_records(async_db_session, runtime_context)

    dashboard_result = await _create_dashboard(async_db_session, runnable_config)
    dashboard_id = dashboard_result["dashboard_id"]

    await dashboard_base.update_dashboard_layout.ainvoke(
        {"dashboard_id": dashboard_id, "cols": 16, "gap": 24},
        config=runnable_config,
    )

    config_result = await dashboard_base.get_dashboard_config.ainvoke(
        {"dashboard_id": dashboard_id},
        config=runnable_config,
    )
    config = json.loads(config_result.content)

    assert config["config"]["layout"]["cols"] == 16
    assert config["config"]["layout"]["gap"] == 24


@pytest.mark.asyncio
async def test_dashboard_filter_tools_flow(async_db_session, runtime_context, runnable_config, monkeypatch):
    monkeypatch.setattr(dashboard_base, "app_db_session", lambda: _SessionContext(async_db_session))
    monkeypatch.setattr(dashboard_filter, "app_db_session", lambda: _SessionContext(async_db_session))
    await _seed_base_records(async_db_session, runtime_context)

    created_dashboard = await dashboard_base.create_dashboard.ainvoke(
        {"title": "Filter Integration", "description": "filter tools"},
        config=runnable_config,
    )
    dashboard_id = json.loads(created_dashboard.content)["dashboard_id"]

    added = await dashboard_filter.add_filter_to_dashboard.ainvoke(
        {
            "dashboard_id": dashboard_id,
            "filter_data": {
                "name": "Status",
                "type": "dropdown_static",
                "param_key": "status",
                "options": [{"label": "Open", "value": "open"}, {"label": "Closed", "value": "closed"}],
            },
        },
        config=runnable_config,
    )
    added_payload = json.loads(added.content)
    filter_id = added_payload["id"]

    updated = await dashboard_filter.update_filter_on_dashboard.ainvoke(
        {
            "dashboard_id": dashboard_id,
            "filter_id": filter_id,
            "updates": {"name": "Issue Status"},
        },
        config=runnable_config,
    )
    updated_payload = json.loads(updated.content)
    assert updated_payload["id"] == filter_id

    removed = await dashboard_filter.remove_filter_from_dashboard.ainvoke(
        {"dashboard_id": dashboard_id, "filter_id": filter_id},
        config=runnable_config,
    )
    removed_payload = json.loads(removed.content)
    assert removed_payload["deleted"] is True


@pytest.mark.asyncio
async def test_add_widget_to_dashboard_chart_types_persist_correctly(
    async_db_session,
    runtime_context,
    runnable_config,
    monkeypatch,
):
    monkeypatch.setattr(
        dashboard_base,
        "app_db_session",
        lambda: _SessionContext(async_db_session),
    )
    monkeypatch.setattr(
        dashboard_widget,
        "app_db_session",
        lambda: _SessionContext(async_db_session),
    )
    await _seed_base_records(async_db_session, runtime_context)

    dashboard_result = await _create_dashboard(async_db_session, runnable_config)
    dashboard_id = dashboard_result["dashboard_id"]

    chart_cases = [
        {
            "chart_type": "line",
            "query": "SELECT order_date, SUM(amount) AS sales FROM orders GROUP BY order_date",
            "field_mapping": {"x_axis": "order_date", "series": ["sales"]},
        },
        {
            "chart_type": "bar",
            "query": "SELECT category, SUM(amount) AS total_sales FROM orders GROUP BY category",
            "field_mapping": {"x_axis": "category", "series": ["total_sales"]},
        },
        {
            "chart_type": "area",
            "query": "SELECT dt, SUM(visits) AS visits FROM traffic GROUP BY dt",
            "field_mapping": {"x_axis": "dt", "series": ["visits"]},
        },
        {
            "chart_type": "pie",
            "query": "SELECT product, SUM(quantity) AS total_qty FROM orders GROUP BY product",
            "field_mapping": {"x_axis": "product", "value": "total_qty"},
        },
        {
            "chart_type": "scatter",
            "query": "SELECT age, salary, years_exp, department FROM employees",
            "field_mapping": {
                "x_axis": "age",
                "y_axis": "salary",
                "size": "years_exp",
                "color": "department",
            },
        },
        {
            "chart_type": "heatmap",
            "query": "SELECT weekday, hour_bucket, cnt FROM heat",
            "field_mapping": {"x_axis": "weekday", "y_axis": "hour_bucket", "value": "cnt"},
        },
        {
            "chart_type": "stacked_bar",
            "query": "SELECT month, web, store FROM sales_mix",
            "field_mapping": {"x_axis": "month", "series": ["web", "store"]},
        },
        {
            "chart_type": "grouped_bar",
            "query": "SELECT month, new_users, retained_users FROM users_mix",
            "field_mapping": {"x_axis": "month", "series": ["new_users", "retained_users"]},
        },
        {
            "chart_type": "multi_line",
            "query": "SELECT month, mrr, arr FROM rev_trend",
            "field_mapping": {"x_axis": "month", "series": ["mrr", "arr"]},
        },
        {
            "chart_type": "multi_area",
            "query": "SELECT month, west, east FROM region_trend",
            "field_mapping": {"x_axis": "month", "series": ["west", "east"]},
        },
        {
            "chart_type": "gauge",
            "query": "SELECT uptime_ratio FROM metrics",
            "field_mapping": {"value": "uptime_ratio"},
        },
    ]

    for chart_case in chart_cases:
        await dashboard_widget.add_widget_to_dashboard.ainvoke(
            {
                "dashboard_id": dashboard_id,
                "widget_data": {
                    "widget_type": "chart",
                    "chart_type": chart_case["chart_type"],
                    "query": chart_case["query"],
                    "field_mapping": chart_case["field_mapping"],
                },
            },
            config=runnable_config,
        )

    config_result = await dashboard_base.get_dashboard_config.ainvoke(
        {"dashboard_id": dashboard_id},
        config=runnable_config,
    )
    config = json.loads(config_result.content)
    widgets = config["config"]["widgets"]

    assert len(widgets) == len(chart_cases)

    def _normalize_field_mapping(mapping: dict | None) -> dict | None:
        if mapping is None:
            return None
        return {
            "x_axis": mapping.get("x_axis") or mapping.get("xAxis"),
            "y_axis": mapping.get("y_axis") or mapping.get("yAxis"),
            "series": mapping.get("series"),
            "value": mapping.get("value"),
            "size": mapping.get("size"),
            "color": mapping.get("color"),
        }

    def _project_widget(widget: dict) -> dict:
        return {
            "type": widget.get("type"),
            "chart_type": widget.get("chartType"),
            "field_mapping": _normalize_field_mapping(widget.get("fieldMapping")),
        }

    expected = [
        {
            "type": "chart",
            "chart_type": chart_case["chart_type"],
            "field_mapping": {
                "x_axis": chart_case["field_mapping"].get("x_axis"),
                "y_axis": chart_case["field_mapping"].get("y_axis"),
                "series": chart_case["field_mapping"].get("series"),
                "value": chart_case["field_mapping"].get("value"),
                "size": chart_case["field_mapping"].get("size"),
                "color": chart_case["field_mapping"].get("color"),
            },
        }
        for chart_case in chart_cases
    ]

    actual = [_project_widget(widget) for widget in widgets]
    for idx, (actual_item, expected_item) in enumerate(zip(actual, expected, strict=True)):
        assert actual_item == expected_item, (
            "Widget mismatch at index "
            f"{idx}:\n"
            f"expected={json.dumps(expected_item, ensure_ascii=False)}\n"
            f"actual={json.dumps(actual_item, ensure_ascii=False)}"
        )


@pytest.mark.asyncio
async def test_add_widget_persists_core_fields_and_display_config(
    async_db_session,
    runtime_context,
    runnable_config,
    monkeypatch,
):
    monkeypatch.setattr(
        dashboard_base,
        "app_db_session",
        lambda: _SessionContext(async_db_session),
    )
    monkeypatch.setattr(
        dashboard_widget,
        "app_db_session",
        lambda: _SessionContext(async_db_session),
    )
    await _seed_base_records(async_db_session, runtime_context)

    dashboard_result = await _create_dashboard(async_db_session, runnable_config)
    dashboard_id = dashboard_result["dashboard_id"]

    add_chart_result = await dashboard_widget.add_widget_to_dashboard.ainvoke(
        {
            "dashboard_id": dashboard_id,
            "widget_data": {
                "widget_type": "chart",
                "chart_type": "line",
                "position": {"x": 2, "y": 1, "w": 8, "h": 5},
                "data_source_id": 42,
                "query": "SELECT order_date, SUM(amount) AS daily_sales FROM orders GROUP BY order_date",
                "field_mapping": {
                    "x_axis": "order_date",
                    "series": ["daily_sales"],
                    "extra": {"display_name": "Daily Sales"},
                },
                "display_config": {
                    "title": "Daily Sales Trend",
                    "x_label": "Date",
                    "y_label": "Sales",
                    "series_labels": {"daily_sales": "Daily Sales"},
                    "show_legend": True,
                    "legend_position": "top",
                    "description": "Sales by day",
                },
            },
        },
        config=runnable_config,
    )
    add_chart_payload = json.loads(add_chart_result.content)

    add_table_result = await dashboard_widget.add_widget_to_dashboard.ainvoke(
        {
            "dashboard_id": dashboard_id,
            "widget_data": {
                "widget_type": "table",
                "position": {"x": 0, "y": 6, "w": 12, "h": 6},
                "data_source_id": 7,
                "query": "SELECT region, revenue FROM sales_summary",
                "display_config": {
                    "table": {
                        "columns": [
                            {
                                "field": "region",
                                "label": "Region",
                                "align": "left",
                            },
                            {
                                "field": "revenue",
                                "label": "Revenue",
                                "align": "right",
                                "format": {
                                    "format_type": "currency",
                                    "currency": "USD",
                                    "precision": 0,
                                },
                            },
                        ],
                        "show_header": True,
                        "show_row_numbers": True,
                        "zebra_stripes": True,
                        "compact": False,
                    }
                },
            },
        },
        config=runnable_config,
    )
    add_table_payload = json.loads(add_table_result.content)

    config_result = await dashboard_base.get_dashboard_config.ainvoke(
        {"dashboard_id": dashboard_id},
        config=runnable_config,
    )
    config = json.loads(config_result.content)
    widgets = config["config"]["widgets"]

    def _find_widget(widget_id: str) -> dict:
        return next(w for w in widgets if w["id"] == widget_id)

    chart_widget = _find_widget(add_chart_payload["id"])
    assert chart_widget["type"] == "chart"
    assert chart_widget["chartType"] == "line"
    assert chart_widget["position"] == {"x": 2, "y": 1, "w": 8, "h": 5}
    assert chart_widget["dataSourceId"] == 42
    assert chart_widget["query"] == "SELECT order_date, SUM(amount) AS daily_sales FROM orders GROUP BY order_date"
    assert chart_widget["fieldMapping"] == {
        "xAxis": "order_date",
        "yAxis": None,
        "series": ["daily_sales"],
        "value": None,
        "size": None,
        "color": None,
        "extra": {"display_name": "Daily Sales"},
    }
    assert chart_widget["displayConfig"] == {
        "title": "Daily Sales Trend",
        "xLabel": "Date",
        "yLabel": "Sales",
        "seriesLabels": {"daily_sales": "Daily Sales"},
        "showLegend": True,
        "legendPosition": "top",
        "metricFormat": None,
        "description": "Sales by day",
        "scatter": None,
        "gauge": None,
        "table": None,
    }

    table_widget = _find_widget(add_table_payload["id"])
    assert table_widget["type"] == "table"
    assert table_widget["chartType"] is None
    assert table_widget["position"] == {"x": 0, "y": 6, "w": 12, "h": 6}
    assert table_widget["dataSourceId"] == 7
    assert table_widget["query"] == "SELECT region, revenue FROM sales_summary"
    assert table_widget["fieldMapping"] is None
    assert table_widget["displayConfig"]["table"] == {
        "columns": [
            {
                "field": "region",
                "label": "Region",
                "align": "left",
                "width": None,
                "minWidth": None,
                "maxWidth": None,
                "format": None,
            },
            {
                "field": "revenue",
                "label": "Revenue",
                "align": "right",
                "width": None,
                "minWidth": None,
                "maxWidth": None,
                "format": {
                    "formatType": "currency",
                    "precision": 0,
                    "currency": "USD",
                    "dateFormat": None,
                    "prefix": None,
                    "suffix": None,
                    "nullDisplay": None,
                    "trueLabel": None,
                    "falseLabel": None,
                },
            },
        ],
        "defaultFormat": None,
        "showHeader": True,
        "showRowNumbers": True,
        "zebraStripes": True,
        "compact": False,
    }


@pytest.mark.asyncio
async def test_update_widget_persists_field_mapping_and_display_config_changes(
    async_db_session,
    runtime_context,
    runnable_config,
    monkeypatch,
):
    monkeypatch.setattr(
        dashboard_base,
        "app_db_session",
        lambda: _SessionContext(async_db_session),
    )
    monkeypatch.setattr(
        dashboard_widget,
        "app_db_session",
        lambda: _SessionContext(async_db_session),
    )
    await _seed_base_records(async_db_session, runtime_context)

    dashboard_result = await _create_dashboard(async_db_session, runnable_config)
    dashboard_id = dashboard_result["dashboard_id"]

    add_result = await dashboard_widget.add_widget_to_dashboard.ainvoke(
        {
            "dashboard_id": dashboard_id,
            "widget_data": {
                "widget_type": "chart",
                "chart_type": "bar",
                "position": {"x": 0, "y": 0, "w": 6, "h": 4},
                "query": "SELECT category, SUM(amount) AS total_sales FROM orders GROUP BY category",
                "field_mapping": {"x_axis": "category", "series": ["total_sales"]},
                "display_config": {
                    "title": "Total Sales",
                    "x_label": "Category",
                    "y_label": "Amount",
                    "series_labels": {"total_sales": "Total Sales"},
                },
            },
        },
        config=runnable_config,
    )
    add_payload = json.loads(add_result.content)

    update_result = await dashboard_widget.update_widget.ainvoke(
        {
            "dashboard_id": dashboard_id,
            "widget_id": add_payload["id"],
            "chart_type": "scatter",
            "position": {"x": 1, "y": 2, "w": 10, "h": 6},
            "query": "SELECT age, salary, years_exp, department FROM employees",
            "field_mapping": {
                "x_axis": "age",
                "y_axis": "salary",
                "size": "years_exp",
                "color": "department",
            },
            "display_config": {
                "title": "Compensation vs Experience",
                "x_label": "Age",
                "y_label": "Salary",
                "scatter": {
                    "size_range": [6, 40],
                    "color_scale_type": "ordinal",
                    "color_range": ["#0ea5e9", "#22c55e"],
                },
            },
        },
        config=runnable_config,
    )
    update_payload = json.loads(update_result.content)
    assert update_payload["position"] == {"x": 1, "y": 2, "w": 10, "h": 6}
    config_result = await dashboard_base.get_dashboard_config.ainvoke(
        {"dashboard_id": dashboard_id},
        config=runnable_config,
    )
    config = json.loads(config_result.content)
    widget = next(w for w in config["config"]["widgets"] if w["id"] == add_payload["id"])

    assert widget["type"] == "chart"
    assert widget["chartType"] == "scatter"
    assert widget["position"] == {"x": 1, "y": 2, "w": 10, "h": 6}
    assert widget["query"] == "SELECT age, salary, years_exp, department FROM employees"
    assert widget["fieldMapping"] == {
        "xAxis": "age",
        "yAxis": "salary",
        "series": None,
        "value": None,
        "size": "years_exp",
        "color": "department",
        "extra": None,
    }
    assert widget["displayConfig"] == {
        "title": "Compensation vs Experience",
        "xLabel": "Age",
        "yLabel": "Salary",
        "seriesLabels": None,
        "showLegend": True,
        "legendPosition": None,
        "metricFormat": None,
        "description": None,
        "scatter": {
            "sizeRange": [6, 40],
            "colorScaleType": "ordinal",
            "colorRange": ["#0ea5e9", "#22c55e"],
        },
        "gauge": None,
        "table": None,
    }


@pytest.mark.asyncio
async def test_dashboard_tools_access_respects_share_permission(
    async_db_session,
    runtime_context,
    runnable_config,
    monkeypatch,
):
    monkeypatch.setattr(dashboard_base, "app_db_session", lambda: _SessionContext(async_db_session))
    await _seed_base_records(async_db_session, runtime_context)

    dashboard_result = await _create_dashboard(async_db_session, runnable_config)
    dashboard_id = dashboard_result["dashboard_id"]
    _artifact_id = dashboard_result["artifact"]["id"]

    other_user_id = 459
    other_thread_id = "thread_test_459_other"
    other_user = User(
        id=other_user_id,
        username="dashboard_reader",
        email="dashboard_reader@example.com",
        hashed_password="test_password_hash",
        role="analyst",
        tenant_id=runtime_context.user.tenant_id,
    )
    other_thread = ChatThread(
        id=other_thread_id,
        tenant_id=runtime_context.tenant.tenant_id,
        user_id=other_user_id,
        agent_id=runtime_context.agent_id,
        title="dashboard reader thread",
    )
    async_db_session.add_all([other_user, other_thread])
    await async_db_session.commit()
    other_user_config = build_runnable_config_for_actor(
        runtime_context,
        user_id=other_user_id,
        username="dashboard_reader",
        role="analyst",
        thread_id=other_thread_id,
    )

    with pytest.raises(AuthorizationError):
        await dashboard_base.get_dashboard_config.ainvoke(
            {"dashboard_id": dashboard_id},
            config=other_user_config,
        )

    async_db_session.add(
        AclGrantModel(
            tenant_id=runtime_context.user.tenant_id,
            resource_type="dashboard",
            resource_id=dashboard_id,
            principal_type="user",
            principal_id=str(other_user_id),
            permission="read",
            effect="allow",
            created_by=runtime_context.user.user_id,
        )
    )
    await async_db_session.commit()

    shared_read = await dashboard_base.get_dashboard_config.ainvoke(
        {"dashboard_id": dashboard_id},
        config=other_user_config,
    )
    shared_read_payload = json.loads(shared_read.content)
    assert shared_read_payload["dashboard_id"] == dashboard_id

    with pytest.raises(AuthorizationError):
        await dashboard_base.update_dashboard_layout.ainvoke(
            {"dashboard_id": dashboard_id, "cols": 16},
            config=other_user_config,
        )

    share = (
        await async_db_session.execute(
            select(AclGrantModel).where(
                AclGrantModel.tenant_id == runtime_context.user.tenant_id,
                AclGrantModel.resource_type == "dashboard",
                AclGrantModel.resource_id == dashboard_id,
                AclGrantModel.principal_type == "user",
                AclGrantModel.principal_id == str(other_user_id),
                AclGrantModel.effect == "allow",
            )
        )
    ).scalar_one()
    share.permission = "write"
    await async_db_session.commit()

    updated = await dashboard_base.update_dashboard_layout.ainvoke(
        {"dashboard_id": dashboard_id, "cols": 16},
        config=other_user_config,
    )
    updated_payload = json.loads(updated.content)
    assert updated_payload["layout"]["cols"] == 16


@pytest.mark.asyncio
async def test_validate_widget_query_success_omits_filters_on_success(
    async_db_session,
    runtime_context,
    runnable_config,
    monkeypatch,
):
    monkeypatch.setattr(dashboard_widget, "app_db_session", lambda: _SessionContext(async_db_session))
    await _seed_base_records(async_db_session, runtime_context)

    async def _fake_preview_dashboard_sql_for_actor(self, **kwargs):
        return {"columns": [{"name": "total", "type": "int64"}], "rows": [{"total": 123}]}

    monkeypatch.setattr(
        dashboard_widget.DashboardService,
        "preview_dashboard_sql_for_actor",
        _fake_preview_dashboard_sql_for_actor,
    )

    result = await dashboard_widget.validate_widget_query.ainvoke(
        {
            "dashboard_id": 1,
            "data_source_id": 6,
            "query": "SELECT 123 AS total",
        },
        config=runnable_config,
    )
    payload = json.loads(result.content)

    assert result.status == ToolResultStatus.SUCCESS
    assert payload["valid"] is True
    assert "filters" not in payload
    assert payload["rows"] == [{"total": 123}]


@pytest.mark.asyncio
async def test_validate_widget_query_failure_returns_filters_metadata(
    async_db_session,
    runtime_context,
    runnable_config,
    monkeypatch,
):
    monkeypatch.setattr(dashboard_widget, "app_db_session", lambda: _SessionContext(async_db_session))
    await _seed_base_records(async_db_session, runtime_context)

    async def _fake_preview_dashboard_sql_for_actor(self, **kwargs):
        raise ValidationError("Query contains $time_filter but no filters are configured")

    class _Dashboard:
        class _Config:
            filters = []

        config = _Config()

    async def _fake_get_dashboard_for_actor(self, dashboard_id, *, actor):
        return _Dashboard()

    monkeypatch.setattr(
        dashboard_widget.DashboardService,
        "preview_dashboard_sql_for_actor",
        _fake_preview_dashboard_sql_for_actor,
    )
    monkeypatch.setattr(
        dashboard_widget.DashboardService,
        "get_dashboard_for_actor",
        _fake_get_dashboard_for_actor,
    )

    result = await dashboard_widget.validate_widget_query.ainvoke(
        {
            "dashboard_id": 1,
            "data_source_id": 6,
            "query": "SELECT * FROM t WHERE $time_filter(:time, created_at)",
        },
        config=runnable_config,
    )

    assert result.status == ToolResultStatus.ERROR
    assert "no filters are configured" in result.content
    assert result.metadata["filters"] == []
