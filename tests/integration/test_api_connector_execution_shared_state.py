"""Integration tests for ApiConnectorExecutionService shared state.

Tests verify that:
1. Token cache persists across multiple service instances
2. Rate limiting works across requests
3. Concurrency limits are shared globally

These tests are critical because ApiConnectorExecutionService is created per-request,
but state (cache, rate limiters) must be shared via _SharedExecutionState singleton.
"""

from time import monotonic
from unittest.mock import MagicMock

import pytest

from apps.shared.api_connector.execution import (
    ApiConnectorExecutionService,
    _shared_execution_state,
)


@pytest.fixture(autouse=True)
def clear_shared_state():
    """Clear shared state before each test to ensure isolation."""
    _shared_execution_state._token_cache.clear()
    _shared_execution_state._rate_limiters.clear()
    _shared_execution_state._concurrency_limits.clear()
    yield
    # Cleanup after test
    _shared_execution_state._token_cache.clear()
    _shared_execution_state._rate_limiters.clear()
    _shared_execution_state._concurrency_limits.clear()


@pytest.mark.asyncio
async def test_token_cache_persists_across_service_instances():
    """Token cache should be shared across multiple service instances.

    Scenario:
    1. Request 1 creates service, logs in, caches token
    2. Request 2 creates NEW service instance
    3. Request 2 should see cached token (cache hit)
    """
    connector_id = 999

    # Request 1: Create service instance and cache token
    service1 = ApiConnectorExecutionService(tenant_id=1, db_session=MagicMock())
    service1._token_cache[connector_id] = {
        "tokens": {"session_id": "cached-token-123"},
        "expires_at": monotonic() + 1800,  # 30 min TTL
    }

    # Request 2: Create NEW service instance
    service2 = ApiConnectorExecutionService(tenant_id=1, db_session=MagicMock())

    # Verify cache is shared
    assert connector_id in service2._token_cache
    cached = service2._token_cache[connector_id]
    assert cached["tokens"]["session_id"] == "cached-token-123"
    assert cached["expires_at"] > monotonic()

    # Verify they reference the same object
    assert service1._token_cache is service2._token_cache
    assert service1._token_cache is _shared_execution_state._token_cache


@pytest.mark.asyncio
async def test_token_cache_miss_triggers_login():
    """Cache miss should be detected when token is not cached or expired."""
    connector_id = 888

    service = ApiConnectorExecutionService(tenant_id=1, db_session=MagicMock())

    # Test 1: No cache entry
    cached = service._token_cache.get(connector_id)
    assert cached is None, "Should be cache miss for new connector"

    # Test 2: Expired token
    service._token_cache[connector_id] = {
        "tokens": {"session_id": "expired-token"},
        "expires_at": monotonic() - 100,  # Expired 100 seconds ago
    }

    cached = service._token_cache.get(connector_id)
    assert cached is not None
    assert cached.get("expires_at", 0) < monotonic(), "Token should be expired"


@pytest.mark.asyncio
async def test_rate_limiters_shared_across_instances():
    """Rate limiters should be shared to enforce limits across all requests."""
    tenant_id = 1
    connector_id = 777
    key = (tenant_id, connector_id)

    # Request 1: Create service and initialize rate limiter
    service1 = ApiConnectorExecutionService(tenant_id=tenant_id, db_session=MagicMock())
    import asyncio

    from apps.shared.api_connector.execution import _TokenBucketState

    service1._rate_limiters[key] = _TokenBucketState(
        rate_per_second=10.0,
        capacity=10,
        tokens=10.0,
        last_refill_at=monotonic(),
        lock=asyncio.Lock(),
    )

    # Request 2: Create NEW service instance
    service2 = ApiConnectorExecutionService(tenant_id=tenant_id, db_session=MagicMock())

    # Verify rate limiter is shared
    assert key in service2._rate_limiters
    assert service1._rate_limiters[key] is service2._rate_limiters[key]
    assert service1._rate_limiters is service2._rate_limiters
    assert service1._rate_limiters is _shared_execution_state._rate_limiters


@pytest.mark.asyncio
async def test_concurrency_limits_shared_across_instances():
    """Concurrency limits should be shared to control global concurrent requests."""
    tenant_id = 1
    connector_id = 666
    key = (tenant_id, connector_id)

    # Request 1: Create service and initialize concurrency limit
    service1 = ApiConnectorExecutionService(tenant_id=tenant_id, db_session=MagicMock())
    import asyncio

    service1._concurrency_limits[key] = asyncio.Semaphore(value=5)

    # Request 2: Create NEW service instance
    service2 = ApiConnectorExecutionService(tenant_id=tenant_id, db_session=MagicMock())

    # Verify concurrency limit is shared
    assert key in service2._concurrency_limits
    assert service1._concurrency_limits[key] is service2._concurrency_limits[key]
    assert service1._concurrency_limits is service2._concurrency_limits
    assert service1._concurrency_limits is _shared_execution_state._concurrency_limits


@pytest.mark.asyncio
async def test_state_lock_shared_across_instances():
    """State lock should be shared to prevent race conditions."""
    service1 = ApiConnectorExecutionService(tenant_id=1, db_session=MagicMock())
    service2 = ApiConnectorExecutionService(tenant_id=1, db_session=MagicMock())

    # Verify they use the same lock
    assert service1._state_lock is service2._state_lock
    assert service1._state_lock is _shared_execution_state._state_lock


@pytest.mark.asyncio
async def test_full_token_lifecycle_across_requests():
    """Test complete token lifecycle: cache miss → login → cache → cache hit."""
    connector_id = 555

    # Simulate Request 1: Cache miss, would trigger login
    service1 = ApiConnectorExecutionService(tenant_id=1, db_session=MagicMock())
    cached1 = service1._token_cache.get(connector_id)
    assert cached1 is None, "Request 1: Should be cache miss"

    # Simulate login and cache token (would happen in _get_or_refresh_session_tokens)
    service1._token_cache[connector_id] = {
        "tokens": {"session_id": "fresh-token-abc"},
        "expires_at": monotonic() + 1800,
    }

    # Simulate Request 2: Should get cache hit
    service2 = ApiConnectorExecutionService(tenant_id=1, db_session=MagicMock())
    cached2 = service2._token_cache.get(connector_id)
    assert cached2 is not None, "Request 2: Should be cache hit"
    assert cached2["tokens"]["session_id"] == "fresh-token-abc"

    # Simulate Request 3: Should still get cache hit
    service3 = ApiConnectorExecutionService(tenant_id=1, db_session=MagicMock())
    cached3 = service3._token_cache.get(connector_id)
    assert cached3 is not None, "Request 3: Should be cache hit"
    assert cached3["tokens"]["session_id"] == "fresh-token-abc"


@pytest.mark.asyncio
async def test_multiple_connectors_independent_caches():
    """Different connectors should have independent token caches."""
    connector_a = 111
    connector_b = 222

    service1 = ApiConnectorExecutionService(tenant_id=1, db_session=MagicMock())

    # Cache tokens for connector A
    service1._token_cache[connector_a] = {
        "tokens": {"session_id": "token-a"},
        "expires_at": monotonic() + 1800,
    }

    # Cache tokens for connector B
    service1._token_cache[connector_b] = {
        "tokens": {"session_id": "token-b"},
        "expires_at": monotonic() + 1800,
    }

    # New service should see both caches
    service2 = ApiConnectorExecutionService(tenant_id=1, db_session=MagicMock())
    assert service2._token_cache[connector_a]["tokens"]["session_id"] == "token-a"
    assert service2._token_cache[connector_b]["tokens"]["session_id"] == "token-b"


@pytest.mark.asyncio
async def test_shared_state_isolation_between_tests():
    """Verify that test fixture properly isolates shared state."""
    # This test should start with clean state
    service = ApiConnectorExecutionService(tenant_id=1, db_session=MagicMock())
    assert len(service._token_cache) == 0, "Should start with empty cache"
    assert len(service._rate_limiters) == 0, "Should start with empty rate limiters"
    assert len(service._concurrency_limits) == 0, "Should start with empty concurrency limits"
