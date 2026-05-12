"""Unit tests for dashboard service query orchestration."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pandas as pd
import pytest

from apps.shared.core.exceptions import ValidationError
from apps.shared.dashboard.domain import (
    DashboardConfig,
    DashboardDomain,
    DashboardFilter,
    DashboardLayout,
    DashboardWidget,
    WidgetPosition,
)
from apps.shared.dashboard.schemas import DashboardFilterValueOverrideDTO
from apps.shared.dashboard.service import DashboardService, apply_filter_value_overrides
from apps.shared.domain.actor import ActorContext


@pytest.mark.asyncio
async def test_query_widget_data_uses_query_data_and_user_context():
    service = DashboardService.create(tenant_id=1, db_session=None)
    widget = DashboardWidget(
        id="w1",
        type="table",
        position=WidgetPosition(x=0, y=0, w=4, h=3),
        query="SELECT id, name FROM orders WHERE region = :region",
        data_source_id=3,
    )
    filters = [
        DashboardFilter(
            id="region",
            name="Region",
            type="dropdown_static",
            param_key="region",
            value="APAC",
        )
    ]

    captured = {}

    class _FakeDataSourceService:
        async def get_data_source_for_actor(self, *, data_source_id, actor):
            return None

        async def query_data_for_actor(self, **kwargs):
            captured.update(kwargs)
            return pd.DataFrame([{"id": 1, "name": "A"}])

    rows = await service.query_widget_data(
        widget,
        data_source_service=_FakeDataSourceService(),
        user_id=123,
        user_role="admin",
        filters=filters,
    )

    assert rows == [{"id": 1, "name": "A"}]
    assert captured["data_source_id"] == 3
    assert captured["actor"].user_id == 123
    assert captured["actor"].user_role == "admin"
    assert captured["max_rows"] == 10000
    assert "region = :region" in captured["sql_query"].lower()


@pytest.mark.asyncio
async def test_query_widget_preview_limits_output_rows():
    service = DashboardService.create(tenant_id=1, db_session=None)
    widget = DashboardWidget(
        id="w2",
        type="table",
        position=WidgetPosition(x=0, y=0, w=4, h=3),
        query="SELECT id FROM orders",
        data_source_id=3,
    )

    captured = {}

    class _FakeDataSourceService:
        async def get_data_source_for_actor(self, *, data_source_id, actor):
            return None

        async def query_data_for_actor(self, **kwargs):
            captured.update(kwargs)
            return pd.DataFrame([{"id": 1}, {"id": 2}, {"id": 3}])

    preview = await service.query_widget_preview(
        widget,
        data_source_service=_FakeDataSourceService(),
        user_id=123,
        user_role="admin",
        limit=2,
    )

    assert len(preview["rows"]) == 2
    assert len(preview["columns"]) == 1
    assert preview["columns"][0]["name"] == "id"
    assert captured["max_rows"] == 2


@pytest.mark.asyncio
async def test_preview_dashboard_sql_for_actor_runs_preview_with_dashboard_filters(monkeypatch):
    service = DashboardService.create(tenant_id=1, db_session=None)
    dashboard = DashboardDomain(
        id=1,
        tenant_id=1,
        name="d",
        description=None,
        config=DashboardConfig(
            layout=DashboardLayout(),
            widgets=[],
            filters=[
                DashboardFilter(
                    id="region",
                    name="Region",
                    type="dropdown_static",
                    param_key="region",
                    value="APAC",
                )
            ],
        ),
        owner_id=1,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    actor = ActorContext(tenant_id=1, user_id=1, user_role="admin")

    async def fake_get_dashboard_for_actor(self, dashboard_id, *, actor):
        assert dashboard_id == 1
        return dashboard

    monkeypatch.setattr(DashboardService, "get_dashboard_for_actor", fake_get_dashboard_for_actor)

    captured = {}

    class _FakeDataSourceService:
        async def get_data_source_for_actor(self, *, data_source_id, actor):
            return None

        async def query_data_for_actor(self, **kwargs):
            captured.update(kwargs)
            return pd.DataFrame([{"a": 1}])

    result = await service.preview_dashboard_sql_for_actor(
        dashboard_id=1,
        data_source_id=5,
        query="SELECT 1 AS a WHERE region = :region",
        actor=actor,
        data_source_service=_FakeDataSourceService(),
        limit=2,
    )

    assert len(result["rows"]) == 1
    assert captured["data_source_id"] == 5
    assert "region" in captured.get("params", {})


@pytest.mark.asyncio
async def test_preview_dashboard_widget_sql_for_actor_merges_overrides(monkeypatch):
    service = DashboardService.create(tenant_id=1, db_session=None)
    w = DashboardWidget(
        id="w1",
        type="table",
        position=WidgetPosition(x=0, y=0, w=4, h=3),
        query="SELECT 1",
        data_source_id=3,
    )
    dashboard = DashboardDomain(
        id=1,
        tenant_id=1,
        name="d",
        description=None,
        config=DashboardConfig(layout=DashboardLayout(), widgets=[w], filters=None),
        owner_id=1,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    actor = ActorContext(tenant_id=1, user_id=1, user_role="admin")

    async def fake_get_dashboard_for_actor(self, dashboard_id, *, actor):
        return dashboard

    monkeypatch.setattr(DashboardService, "get_dashboard_for_actor", fake_get_dashboard_for_actor)

    preview_mock = AsyncMock(return_value={"columns": [{"name": "x", "type": "int64"}], "rows": [{"x": 1}]})
    monkeypatch.setattr(DashboardService, "query_widget_preview", preview_mock)

    await service.preview_dashboard_widget_sql_for_actor(
        dashboard_id=1,
        widget_id="w1",
        actor=actor,
        data_source_service=object(),
        limit=5,
        query="SELECT 2 AS x",
        data_source_id=None,
    )

    widget_arg = preview_mock.call_args[0][0]
    assert widget_arg.query == "SELECT 2 AS x"
    assert widget_arg.data_source_id == 3
    assert preview_mock.call_args.kwargs["limit"] == 5
    assert preview_mock.call_args.kwargs["user_id"] == actor.user_id
    assert preview_mock.call_args.kwargs["user_role"] == actor.user_role


@pytest.mark.asyncio
async def test__query_filter_options_uses_query_data_with_limit():
    service = DashboardService.create(tenant_id=1, db_session=None)
    dashboard_filter = DashboardFilter(
        id="f1",
        name="Region",
        type="dropdown_datasource",
        data_source_id=7,
        options_query="SELECT region AS value, region AS label FROM orders",
    )

    captured = {}

    class _FakeDataSourceService:
        async def get_data_source(self, data_source_id):
            return None

        async def query_data_for_actor(self, **kwargs):
            captured.update(kwargs)
            return pd.DataFrame([{"value": "APAC", "label": "APAC"}])

    options = await service._query_filter_options(
        dashboard_filter,
        data_source_service=_FakeDataSourceService(),
        user_id=123,
        user_role="admin",
        limit=50,
    )

    assert options == [{"value": "APAC", "label": "APAC"}]
    assert captured["data_source_id"] == 7
    assert captured["max_rows"] == 50
    assert "params" not in captured
    assert " limit 50" in captured["sql_query"].lower()


@pytest.mark.asyncio
async def test__query_filter_options_plain_sql_skips_dialect_lookup_and_params():
    service = DashboardService.create(tenant_id=1, db_session=None)
    dashboard_filter = DashboardFilter(
        id="f2",
        name="Region",
        type="dropdown_datasource",
        data_source_id=7,
        options_query="SELECT region AS value, region AS label FROM orders",
    )

    captured = {}

    class _FakeDataSourceService:
        async def get_data_source(self, data_source_id):
            raise AssertionError("get_data_source should not be called for plain SQL options_query")

        async def query_data_for_actor(self, **kwargs):
            captured.update(kwargs)
            return pd.DataFrame([{"value": "EMEA", "label": "EMEA"}])

    options = await service._query_filter_options(
        dashboard_filter,
        data_source_service=_FakeDataSourceService(),
        user_id=123,
        user_role="admin",
        limit=20,
    )

    assert options == [{"value": "EMEA", "label": "EMEA"}]
    assert "params" not in captured
    assert " limit 20" in captured["sql_query"].lower()


@pytest.mark.asyncio
async def test_query_widget_data_rejects_unsafe_query():
    service = DashboardService.create(tenant_id=1, db_session=None)
    widget = DashboardWidget(
        id="w3",
        type="table",
        position=WidgetPosition(x=0, y=0, w=4, h=3),
        query="DELETE FROM orders",
        data_source_id=3,
    )

    class _FakeDataSourceService:
        async def query_data_for_actor(self, **kwargs):
            raise AssertionError("Should not be called")

    with pytest.raises(ValidationError, match="read-only SELECT"):
        await service.query_widget_data(
            widget,
            data_source_service=_FakeDataSourceService(),
            user_id=123,
            user_role="admin",
        )


def test_apply_filter_value_overrides_returns_saved_filters_when_no_overrides():
    filters = [
        DashboardFilter(
            id="filter-region",
            name="Region",
            type="dropdown_static",
            param_key="region",
            value="APAC",
        )
    ]
    assert apply_filter_value_overrides(filters, None) is filters
    assert apply_filter_value_overrides(filters, []) is filters
    assert (
        apply_filter_value_overrides(None, [DashboardFilterValueOverrideDTO(id="filter-region", value="EMEA")]) is None
    )


def test_apply_filter_value_overrides_ignores_unknown_keys():
    filters = [
        DashboardFilter(
            id="filter-region",
            name="Region",
            type="dropdown_static",
            param_key="region",
            value="APAC",
        )
    ]
    merged = apply_filter_value_overrides(
        filters,
        [DashboardFilterValueOverrideDTO(id="filter-other", param_key="channel", value="app")],
    )
    assert merged is not None
    assert merged[0].value == "APAC"


def test_apply_filter_value_overrides_merges_by_id_and_param_key():
    filters = [
        DashboardFilter(
            id="filter-region",
            name="Region",
            type="dropdown_static",
            param_key="region",
            value="APAC",
        ),
        DashboardFilter(
            id="filter-channel",
            name="Channel",
            type="dropdown_static",
            param_key="channel",
            value="web",
        ),
    ]

    merged = apply_filter_value_overrides(
        filters,
        [
            DashboardFilterValueOverrideDTO(id="filter-region", value="EMEA"),
            DashboardFilterValueOverrideDTO(param_key="channel", value="app"),
        ],
    )

    assert merged is not None
    assert merged[0].value == "EMEA"
    assert merged[1].value == "app"
    assert filters[0].value == "APAC"


@pytest.mark.asyncio
async def test_prepare_widget_analytics_query_does_not_execute():
    service = DashboardService.create(tenant_id=1, db_session=None)
    widget = DashboardWidget(
        id="w1",
        type="table",
        position=WidgetPosition(x=0, y=0, w=4, h=3),
        query="SELECT id FROM orders WHERE region = :region",
        data_source_id=3,
    )
    filters = [
        DashboardFilter(
            id="region",
            name="Region",
            type="dropdown_static",
            param_key="region",
            value="APAC",
        )
    ]
    executed = False

    class _FakeManager:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def query(self, sql, params=None):
            nonlocal executed
            executed = True
            raise AssertionError("Databricks query should run after prepare")

    class _FakeDataSourceService:
        async def get_data_source_for_actor(self, *, data_source_id, actor):
            return None

        async def require_read_access_for_actor(self, *, data_source_id, actor):
            return None

        async def get_db_manager(self, data_source_id):
            assert data_source_id == 3
            return _FakeManager()

    prepared = await service.prepare_widget_analytics_query(
        widget,
        data_source_service=_FakeDataSourceService(),
        user_id=123,
        user_role="admin",
        filters=filters,
    )

    assert executed is False
    assert "region = :region" in prepared.sql.lower()
    assert prepared.params["region"] == "APAC"


@pytest.mark.asyncio
async def test_prepare_widget_analytics_query_uses_overridden_filter_value():
    service = DashboardService.create(tenant_id=1, db_session=None)
    widget = DashboardWidget(
        id="w1",
        type="table",
        position=WidgetPosition(x=0, y=0, w=4, h=3),
        query="SELECT id FROM orders WHERE region = :region",
        data_source_id=3,
    )
    saved_filters = [
        DashboardFilter(
            id="filter-region",
            name="Region",
            type="dropdown_static",
            param_key="region",
            value="APAC",
        )
    ]
    merged = apply_filter_value_overrides(
        saved_filters,
        [DashboardFilterValueOverrideDTO(id="filter-region", value="EMEA")],
    )

    class _FakeDataSourceService:
        async def get_data_source_for_actor(self, *, data_source_id, actor):
            return None

        async def require_read_access_for_actor(self, *, data_source_id, actor):
            return None

        async def get_db_manager(self, data_source_id):
            return object()

    prepared = await service.prepare_widget_analytics_query(
        widget,
        data_source_service=_FakeDataSourceService(),
        user_id=123,
        user_role="admin",
        filters=merged,
    )

    assert prepared.params["region"] == "EMEA"
    assert saved_filters[0].value == "APAC"


@pytest.mark.asyncio
async def test_prepared_analytics_query_executes_after_prepare():
    service = DashboardService.create(tenant_id=1, db_session=None)
    widget = DashboardWidget(
        id="w1",
        type="table",
        position=WidgetPosition(x=0, y=0, w=4, h=3),
        query="SELECT id FROM orders",
        data_source_id=3,
    )
    events: list[str] = []

    class _FakeManager:
        async def __aenter__(self):
            events.append("manager_enter")
            return self

        async def __aexit__(self, exc_type, exc, tb):
            events.append("manager_exit")
            return False

        async def query(self, sql, params=None):
            events.append("query")
            return pd.DataFrame([{"id": 1}, {"id": 2}, {"id": 3}])

    class _FakeDataSourceService:
        async def get_data_source_for_actor(self, *, data_source_id, actor):
            return None

        async def require_read_access_for_actor(self, *, data_source_id, actor):
            return None

        async def get_db_manager(self, data_source_id):
            events.append("get_manager")
            return _FakeManager()

    prepared = await service.prepare_widget_analytics_query(
        widget,
        data_source_service=_FakeDataSourceService(),
        user_id=123,
        user_role="admin",
        max_rows=2,
    )
    assert events == ["get_manager"]

    rows = service.materialize_widget_rows(await prepared.execute_dataframe())
    assert rows == [{"id": 1}, {"id": 2}]
    assert events == ["get_manager", "manager_enter", "query", "manager_exit"]
