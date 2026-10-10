"""Configurable HTTP rate limiting (in-memory store; Redis-ready store protocol)."""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict, deque
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Protocol

from fastapi import HTTPException, Request, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response

from apps.shared.core.client_ip import client_ip_key
from apps.shared.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class RateLimitPolicy:
    """Sliding-window limit for a named counter bucket."""

    name: str
    max_events: int
    window_seconds: int
    detail: str = "Too many requests. Please try again later."


class RateLimitStore(Protocol):
    """Storage backend for sliding-window counters (in-memory today, Redis later)."""

    async def prune_and_count(self, bucket_key: str, *, window_seconds: float, now: float) -> int:
        """Drop expired events and return remaining count in the window."""

    async def append(self, bucket_key: str, *, now: float) -> None:
        """Record one event at ``now``."""

    async def clear(self, bucket_key: str) -> None:
        """Remove all events for the bucket."""


class InMemoryRateLimitStore:
    """Process-local sliding-window store."""

    def __init__(self) -> None:
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()

    async def prune_and_count(self, bucket_key: str, *, window_seconds: float, now: float) -> int:
        cutoff = now - window_seconds
        async with self._lock:
            bucket = self._events[bucket_key]
            while bucket and bucket[0] < cutoff:
                bucket.popleft()
            return len(bucket)

    async def append(self, bucket_key: str, *, now: float) -> None:
        async with self._lock:
            self._events[bucket_key].append(now)

    async def clear(self, bucket_key: str) -> None:
        async with self._lock:
            self._events.pop(bucket_key, None)


def _bucket_key(policy: RateLimitPolicy, key: str) -> str:
    return f"{policy.name}:{key}"


class RateLimiter:
    """Policy-aware limiter backed by a :class:`RateLimitStore`."""

    def __init__(self, store: RateLimitStore | None = None):
        self._store = store or InMemoryRateLimitStore()

    async def assert_allowed(self, key: str, policy: RateLimitPolicy) -> None:
        if policy.max_events <= 0 or policy.window_seconds <= 0:
            return
        bucket = _bucket_key(policy, key)
        now = time.monotonic()
        count = await self._store.prune_and_count(bucket, window_seconds=policy.window_seconds, now=now)
        if count >= policy.max_events:
            logger.warning("Rate limit exceeded policy=%s key=%s count=%s", policy.name, key, count)
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=policy.detail)

    async def record(self, key: str, policy: RateLimitPolicy) -> None:
        if policy.max_events <= 0 or policy.window_seconds <= 0:
            return
        bucket = _bucket_key(policy, key)
        await self._store.append(bucket, now=time.monotonic())

    async def reset(self, key: str, policy: RateLimitPolicy) -> None:
        bucket = _bucket_key(policy, key)
        await self._store.clear(bucket)


_default_limiter = RateLimiter()


def get_rate_limiter() -> RateLimiter:
    return _default_limiter


def rate_limit_dependency(
    policy: RateLimitPolicy,
    *,
    key_extractor: Callable[[Request], str] = client_ip_key,
    count_request: bool = True,
):
    """FastAPI dependency: enforce limit per request (optional auto-record)."""

    async def _dependency(request: Request) -> None:
        key = key_extractor(request)
        limiter = get_rate_limiter()
        await limiter.assert_allowed(key, policy)
        if count_request:
            await limiter.record(key, policy)

    return _dependency


def rate_limiter(
    name: str,
    max_events: int,
    window_seconds: int,
    *,
    detail: str = "Too many requests. Please try again later.",
    key_extractor: Callable[[Request], str] = client_ip_key,
    count_request: bool = True,
):
    """Build a FastAPI dependency for a named sliding-window limit.

    Usage::

        @router.post("/login", dependencies=[Depends(rate_limiter("auth.login", 20, 900))])
    """
    policy = RateLimitPolicy(
        name=name,
        max_events=max_events,
        window_seconds=window_seconds,
        detail=detail,
    )
    return rate_limit_dependency(
        policy,
        key_extractor=key_extractor,
        count_request=count_request,
    )


@dataclass(frozen=True, slots=True)
class RouteRateLimitRule:
    """Middleware rule matching path prefix + HTTP methods."""

    path_prefix: str
    policy: RateLimitPolicy
    methods: frozenset[str] = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE"})
    key_extractor: Callable[[Request], str] = client_ip_key


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Apply :class:`RouteRateLimitRule` list before route handlers."""

    def __init__(
        self,
        app,
        *,
        rules: Sequence[RouteRateLimitRule],
        limiter: RateLimiter | None = None,
    ):
        super().__init__(app)
        self._rules = tuple(rules)
        self._limiter = limiter or get_rate_limiter()

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        for rule in self._rules:
            if request.method.upper() not in rule.methods:
                continue
            if not request.url.path.startswith(rule.path_prefix):
                continue
            key = rule.key_extractor(request)
            try:
                await self._limiter.assert_allowed(key, rule.policy)
                await self._limiter.record(key, rule.policy)
            except HTTPException as exc:
                return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
            break
        return await call_next(request)
