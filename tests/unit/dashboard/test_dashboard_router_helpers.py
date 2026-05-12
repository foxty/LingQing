from starlette.requests import Request

from apps.shared.dashboard.domain import DashboardWidget, WidgetPosition
from apps.shared.dashboard.service import _resolve_widget_by_id as _resolve_widget_reference
from apps.tenant_app_service.routers.dashboard import _extract_agent_thread_id


def _widget(widget_id: str) -> DashboardWidget:
    return DashboardWidget(
        id=widget_id,
        type="table",
        position=WidgetPosition(x=0, y=0, w=6, h=4),
        chart_type=None,
        display_config=None,
        options=None,
        data_source_id=None,
        query=None,
        field_mapping=None,
    )


def test_resolve_widget_reference_by_id():
    widgets = [_widget("widget-a"), _widget("widget-b")]

    resolved = _resolve_widget_reference(widgets, "widget-b")

    assert resolved is not None
    assert resolved.id == "widget-b"


def test_resolve_widget_reference_unknown_id_returns_none():
    widgets = [_widget("widget-a"), _widget("widget-b")]

    assert _resolve_widget_reference(widgets, "widget-c") is None


def _request_with_headers(headers: dict[str, str]) -> Request:
    raw_headers = [(k.lower().encode("latin-1"), v.encode("latin-1")) for k, v in headers.items()]
    return Request({"type": "http", "headers": raw_headers})


def test_extract_agent_thread_id_from_direct_header():
    request = _request_with_headers({"x-agent-thread-id": "thread-direct-1"})

    assert _extract_agent_thread_id(request) == "thread-direct-1"


def test_extract_agent_thread_id_invalid_context_returns_none():
    request = _request_with_headers({"x-agent-context": "not-json"})

    assert _extract_agent_thread_id(request) is None
