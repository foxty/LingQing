"""Unit tests for dashboard widget query-data router session lifetime."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pandas as pd
import pytest

from apps.shared.core.exceptions import ResourceNotFoundError
from apps.shared.dashboard.domain import (
    DashboardConfig,
    DashboardDomain,
    DashboardFilter,
    DashboardLayout,
    DashboardWidget,
    WidgetPosition,
)
from apps.shared.dashboard.schemas import DashboardFilterValueOverrideDTO, DashboardWidgetQueryDataRequest
from apps.shared.dashboard.service import PreparedAnalyticsQuery
from apps.shared.schemas.user import UserDTO
from apps.tenant_app_service.routers import dashboard as dashboard_router


def _user() -> UserDTO:
    return UserDTO(id=7, username="tester", role="admin", tenant_id=1, tenant_name="test_tenant")


def _dashboard() -> DashboardDomain:
    widget = DashboardWidget(
        id="widget-orders",
        type="table",
        position=WidgetPosition(x=0, y=0, w=4, h=3),
        query="SELECT id FROM test_orders WHERE region = :region",
        data_source_id=3,
    )
    return DashboardDomain(
        id=2,
        tenant_id=1,
        name="test_dashboard",
        description=None,
        config=DashboardConfig(
            layout=DashboardLayout(),
            widgets=[widget],
            filters=[
                DashboardFilter(
                    id="filter-region",
                    name="Region",
                    type="dropdown_static",
                    param_key="region",
                    value="APAC",
                )
            ],
        ),
        owner_id=7,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


class _TrackingSession:
    def __init__(self, events: list[str]):
        self._events = events

    async def __aenter__(self):
        self._events.append("session_enter")
        return object()

    async def __aexit__(self, exc_type, exc, tb):
        self._events.append("session_exit")
        return False


@pytest.mark.asyncio
async def test_query_data_releases_app_session_before_warehouse_execute(monkeypatch):
    events: list[str] = []
    captured_filters = {}

    dashboard = _dashboard()
    service = AsyncMock()
    service.get_dashboard_for_actor = AsyncMock(return_value=dashboard)

    async def _prepare(widget, data_source_service, user_id, user_role, filters=None, max_rows=10000):
        captured_filters["value"] = filters[0].value if filters else None
        events.append("prepare")

        class _Manager:
            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            async def query(self, sql, params=None):
                events.append("execute")
                return pd.DataFrame([{"id": 1}])

        return PreparedAnalyticsQuery(sql="SELECT 1", params={}, max_rows=max_rows, db_manager=_Manager())

    service.prepare_widget_analytics_query = _prepare
    monkeypatch.setattr(dashboard_router, "app_db_session", lambda: _TrackingSession(events))
    monkeypatch.setattr(dashboard_router, "_create_dashboard_service", lambda db, tenant_id: service)
    monkeypatch.setattr(dashboard_router, "DataSourceService", lambda **kwargs: object())
    monkeypatch.setattr(dashboard_router, "DataSourceRepository", lambda db: object())
    monkeypatch.setattr(dashboard_router, "AssetMetadataRepository", lambda db: object())

    result = await dashboard_router.query_dashboard_widget_data(
        dashboard_id=2,
        widget_id="widget-orders",
        payload=DashboardWidgetQueryDataRequest(
            filters=[DashboardFilterValueOverrideDTO(id="filter-region", value="EMEA")]
        ),
        current_user=_user(),
    )

    assert result == {"data": [{"id": 1}]}
    assert captured_filters["value"] == "EMEA"
    assert events == ["session_enter", "prepare", "session_exit", "execute"]


@pytest.mark.asyncio
async def test_query_data_without_body_uses_saved_filter_values(monkeypatch):
    captured_filters = {}
    dashboard = _dashboard()
    service = AsyncMock()
    service.get_dashboard_for_actor = AsyncMock(return_value=dashboard)

    async def _prepare(widget, data_source_service, user_id, user_role, filters=None, max_rows=10000):
        captured_filters["value"] = filters[0].value if filters else None

        class _Manager:
            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            async def query(self, sql, params=None):
                return pd.DataFrame([])

        return PreparedAnalyticsQuery(sql="SELECT 1", params={}, max_rows=max_rows, db_manager=_Manager())

    service.prepare_widget_analytics_query = _prepare
    monkeypatch.setattr(dashboard_router, "app_db_session", lambda: _TrackingSession([]))
    monkeypatch.setattr(dashboard_router, "_create_dashboard_service", lambda db, tenant_id: service)
    monkeypatch.setattr(dashboard_router, "DataSourceService", lambda **kwargs: object())
    monkeypatch.setattr(dashboard_router, "DataSourceRepository", lambda db: object())
    monkeypatch.setattr(dashboard_router, "AssetMetadataRepository", lambda db: object())

    result = await dashboard_router.query_dashboard_widget_data(
        dashboard_id=2,
        widget_id="widget-orders",
        payload=None,
        current_user=_user(),
    )

    assert result == {"data": []}
    assert captured_filters["value"] == "APAC"


@pytest.mark.asyncio
async def test_query_data_missing_widget_raises(monkeypatch):
    dashboard = _dashboard()
    service = AsyncMock()
    service.get_dashboard_for_actor = AsyncMock(return_value=dashboard)
    monkeypatch.setattr(dashboard_router, "app_db_session", lambda: _TrackingSession([]))
    monkeypatch.setattr(dashboard_router, "_create_dashboard_service", lambda db, tenant_id: service)

    with pytest.raises(ResourceNotFoundError, match="widget-missing"):
        await dashboard_router.query_dashboard_widget_data(
            dashboard_id=2,
            widget_id="widget-missing",
            payload=None,
            current_user=_user(),
        )
