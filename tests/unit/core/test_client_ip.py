"""Client IP resolution behind proxies."""

from starlette.requests import Request

from apps.shared.core.client_ip import client_ip_key, resolve_client_ip


def _request(
    *,
    path: str = "/auth/login",
    headers: list[tuple[bytes, bytes]] | None = None,
    client: tuple[str, int] | None = ("203.0.113.10", 44000),
) -> Request:
    scope = {
        "type": "http",
        "method": "POST",
        "path": path,
        "headers": headers or [],
        "client": client,
    }
    return Request(scope)


def test_resolve_client_ip_prefers_x_real_ip():
    req = _request(headers=[(b"x-real-ip", b"198.51.100.2")], client=("10.0.0.5", 1234))
    assert resolve_client_ip(req) == "198.51.100.2"


def test_resolve_client_ip_parses_x_forwarded_for_leftmost():
    req = _request(headers=[(b"x-forwarded-for", b"203.0.113.9, 10.0.0.1")])
    assert resolve_client_ip(req) == "203.0.113.9"


def test_resolve_client_ip_falls_back_to_peer():
    req = _request(client=("127.0.0.1", 8000))
    assert resolve_client_ip(req) == "127.0.0.1"


def test_client_ip_key_logs_and_returns_unknown_when_unresolved(caplog):
    req = _request(client=None)
    assert client_ip_key(req) == "unknown"
    assert any("Could not resolve client IP" in rec.message for rec in caplog.records)
