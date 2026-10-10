"""Unit tests for apps.shared.core.rate_limit."""

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request

from apps.shared.core import rate_limit as rl


def _request(*, host: str | None = "1.2.3.4", path: str = "/x", method: str = "POST") -> Request:
    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "headers": [],
        "client": (host, 12345) if host else None,
    }
    return Request(scope)


@pytest.mark.asyncio
async def test_rate_limiter_disabled_when_max_events_zero():
    limiter = rl.RateLimiter(store=rl.InMemoryRateLimitStore())
    policy = rl.RateLimitPolicy(name="off", max_events=0, window_seconds=60)
    for _ in range(5):
        await limiter.assert_allowed("k", policy)
        await limiter.record("k", policy)


@pytest.mark.asyncio
async def test_rate_limiter_blocks_when_at_capacity():
    limiter = rl.RateLimiter(store=rl.InMemoryRateLimitStore())
    policy = rl.RateLimitPolicy(name="cap", max_events=2, window_seconds=60)
    await limiter.record("ip-a", policy)
    await limiter.record("ip-a", policy)
    with pytest.raises(HTTPException) as exc:
        await limiter.assert_allowed("ip-a", policy)
    assert exc.value.status_code == 429


@pytest.mark.asyncio
async def test_rate_limiter_reset_clears_bucket():
    limiter = rl.RateLimiter(store=rl.InMemoryRateLimitStore())
    policy = rl.RateLimitPolicy(name="reset", max_events=1, window_seconds=60)
    await limiter.record("ip-b", policy)
    with pytest.raises(HTTPException):
        await limiter.assert_allowed("ip-b", policy)
    await limiter.reset("ip-b", policy)
    await limiter.assert_allowed("ip-b", policy)


@pytest.mark.asyncio
async def test_in_memory_store_prunes_expired_events():
    store = rl.InMemoryRateLimitStore()
    await store.append("bucket", now=100.0)
    await store.append("bucket", now=101.0)
    count = await store.prune_and_count("bucket", window_seconds=60, now=250.0)
    assert count == 0


def test_client_ip_key_fallback():
    assert rl.client_ip_key(_request(host=None)) == "unknown"
    assert rl.client_ip_key(_request(host="9.9.9.9")) == "9.9.9.9"


def test_client_ip_key_uses_x_real_ip_header():
    req = _request(host="10.0.0.5")
    req.scope["headers"] = [(b"x-real-ip", b"198.51.100.3")]
    assert rl.client_ip_key(req) == "198.51.100.3"


@pytest.mark.asyncio
async def test_rate_limiter_builds_working_dependency(monkeypatch):
    limiter = rl.RateLimiter(store=rl.InMemoryRateLimitStore())
    monkeypatch.setattr(rl, "get_rate_limiter", lambda: limiter)
    dep = rl.rate_limiter("helper", max_events=1, window_seconds=60)
    req = _request(host="10.0.0.3")
    await dep(req)
    with pytest.raises(HTTPException) as exc:
        await dep(req)
    assert exc.value.status_code == 429


@pytest.mark.asyncio
async def test_rate_limit_dependency_enforces_and_records(monkeypatch):
    limiter = rl.RateLimiter(store=rl.InMemoryRateLimitStore())
    monkeypatch.setattr(rl, "get_rate_limiter", lambda: limiter)
    policy = rl.RateLimitPolicy(name="dep", max_events=2, window_seconds=60)
    dep = rl.rate_limit_dependency(policy)

    req = _request(host="10.0.0.2")
    await dep(req)
    await dep(req)
    with pytest.raises(HTTPException) as exc:
        await dep(req)
    assert exc.value.status_code == 429


@pytest.mark.asyncio
async def test_rate_limit_middleware_applies_matching_rule():
    limiter = rl.RateLimiter(store=rl.InMemoryRateLimitStore())
    policy = rl.RateLimitPolicy(name="mw", max_events=1, window_seconds=60)

    app = FastAPI()

    @app.get("/auth/login")
    async def ok():
        return {"ok": True}

    app.add_middleware(
        rl.RateLimitMiddleware,
        rules=[rl.RouteRateLimitRule(path_prefix="/auth/login", policy=policy, methods=frozenset({"GET"}))],
        limiter=limiter,
    )

    client = TestClient(app, raise_server_exceptions=False)
    assert client.get("/auth/login").status_code == 200
    assert client.get("/auth/login").status_code == 429


@pytest.mark.asyncio
async def test_rate_limit_middleware_skips_non_matching_path():
    limiter = rl.RateLimiter(store=rl.InMemoryRateLimitStore())
    policy = rl.RateLimitPolicy(name="mw-skip", max_events=1, window_seconds=60)

    app = FastAPI()

    @app.get("/other")
    async def ok():
        return {"ok": True}

    app.add_middleware(
        rl.RateLimitMiddleware,
        rules=[rl.RouteRateLimitRule(path_prefix="/auth/login", policy=policy, methods=frozenset({"GET"}))],
        limiter=limiter,
    )

    client = TestClient(app)
    assert client.get("/other").status_code == 200
    assert client.get("/other").status_code == 200
