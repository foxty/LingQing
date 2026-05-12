"""Unit tests for HTTP request context helpers."""

from apps.shared.core.request_context import format_request_context, get_or_create_request_id


class _State:
    pass


class _Request:
    def __init__(self, *, headers: dict | None = None, path: str = "/documents", method: str = "GET"):
        self.headers = headers or {}
        self.state = _State()
        self.method = method
        self.url = type("URL", (), {"path": path})()
        self.cookies: dict[str, str] = {}


def test_get_or_create_request_id_uses_inbound_header():
    request = _Request(headers={"X-Request-ID": "abc-123"})
    assert get_or_create_request_id(request) == "abc-123"
    assert request.state.request_id == "abc-123"


def test_get_or_create_request_id_generates_when_missing():
    request = _Request()
    request_id = get_or_create_request_id(request)
    assert isinstance(request_id, str)
    assert len(request_id) >= 8
    assert request.state.request_id == request_id


def test_format_request_context_includes_request_id_and_route():
    request = _Request(headers={"X-Request-ID": "req-42"}, path="/documents/upload", method="POST")
    context = format_request_context(request)
    assert "request_id=req-42" in context
    assert "method=POST" in context
    assert "path=/documents/upload" in context
    assert "tenant=unknown" in context
