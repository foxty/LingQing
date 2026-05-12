"""Unit tests for ApiConnectorExecutionService."""


import pytest

from apps.shared.api_connector.domain import RatePolicyDomain
from apps.shared.api_connector.execution import ApiConnectorExecutionService
from apps.shared.api_connector.schemas import ApiOperationCallParameters
from apps.shared.api_connector.service import ApiConnectorService
from apps.shared.core.exceptions import ResourceNotFoundError, ValidationError
from apps.shared.db.models import Tenant, User
from apps.shared.domain.actor import ActorContext


@pytest.mark.asyncio
async def test_execute_operation_injects_api_key_and_path_params(async_db_session, monkeypatch):
    tenant = Tenant(name="tenant_api_exec_1", slug="tenant_api_exec_1", config=None)
    async_db_session.add(tenant)
    await async_db_session.flush()

    user = User(username="eve", email=None, hashed_password="hashed", role="admin", tenant_id=tenant.id)
    async_db_session.add(user)
    await async_db_session.flush()

    service = ApiConnectorService(tenant_id=tenant.id, db_session=async_db_session)
    connector = await service.create_connector(
        owner_id=user.id,
        name="exec-api",
        description=None,
        base_url="https://8.8.8.8",
        auth_type="api_key",
        auth_config={"key_name": "X-API-Key", "key_value": "token-123"},
        rate_policy=RatePolicyDomain.from_raw({"timeout_ms": 8000}),
        schema_source_type="manual",
        schema_source_url=None,
    )
    operation = await service.add_manual_operation_for_actor(
        connector_id=connector.id,
        actor=ActorContext(tenant_id=tenant.id, user_id=user.id, user_role=user.role),
        method="GET",
        path_template="/orders/{id}",
        operation_id="getOrder",
        summary="get order",
        description=None,
        tags=["orders"],
        request_schema={"type": "object"},
        response_schema={"type": "object"},
    )

    captured = {}

    async def _fake_send(self, *, method, url, headers, query, body, timeout_ms):
        captured["method"] = method
        captured["url"] = url
        captured["headers"] = headers
        captured["query"] = query
        captured["body"] = body
        captured["timeout_ms"] = timeout_ms
        return 200, {"content-type": "application/json"}, {"ok": True}

    monkeypatch.setattr(ApiConnectorExecutionService, "_send_http_request", _fake_send)

    exec_service = ApiConnectorExecutionService(tenant_id=tenant.id, db_session=async_db_session)
    result = await exec_service.execute_operation_for_actor(
        operation_uid=operation.operation_uid,
        actor=ActorContext(tenant_id=tenant.id, user_id=user.id, user_role=user.role),
        parameters=ApiOperationCallParameters(path={"id": "123"}, query={"expand": "full"}),
    )

    assert result.error is None
    assert result.status_code == 200
    assert captured["method"] == "GET"
    assert captured["url"].endswith("/orders/123")
    assert captured["headers"]["X-API-Key"] == "token-123"
    assert captured["query"] == {"expand": "full"}


@pytest.mark.asyncio
async def test_execute_operation_returns_error_for_missing_path_param(async_db_session):
    tenant = Tenant(name="tenant_api_exec_2", slug="tenant_api_exec_2", config=None)
    async_db_session.add(tenant)
    await async_db_session.flush()

    user = User(username="frank", email=None, hashed_password="hashed", role="admin", tenant_id=tenant.id)
    async_db_session.add(user)
    await async_db_session.flush()

    service = ApiConnectorService(tenant_id=tenant.id, db_session=async_db_session)
    connector = await service.create_connector(
        owner_id=user.id,
        name="exec-api-2",
        description=None,
        base_url="https://8.8.8.8",
        auth_type="none",
        auth_config={},
        rate_policy=RatePolicyDomain.from_raw({}),
        schema_source_type="manual",
        schema_source_url=None,
    )
    operation = await service.add_manual_operation_for_actor(
        connector_id=connector.id,
        actor=ActorContext(tenant_id=tenant.id, user_id=user.id, user_role=user.role),
        method="GET",
        path_template="/orders/{id}",
        operation_id="getOrder",
        summary="get order",
        description=None,
        tags=["orders"],
        request_schema={"type": "object"},
        response_schema={"type": "object"},
    )

    exec_service = ApiConnectorExecutionService(tenant_id=tenant.id, db_session=async_db_session)
    result = await exec_service.execute_operation_for_actor(
        operation_uid=operation.operation_uid,
        actor=ActorContext(tenant_id=tenant.id, user_id=user.id, user_role=user.role),
        parameters=ApiOperationCallParameters(),
    )

    assert result.status_code == 0
    assert result.error is not None
    assert "Missing required path parameters" in result.error


def test_validate_base_url_blocks_private_hosts():
    with pytest.raises(ValidationError, match="loopback"):
        ApiConnectorExecutionService._validate_base_url("http://127.0.0.1:8080")


@pytest.mark.asyncio
async def test_execute_operation_retries_on_retryable_status(async_db_session, monkeypatch):
    tenant = Tenant(name="tenant_api_exec_retry", slug="tenant_api_exec_retry", config=None)
    async_db_session.add(tenant)
    await async_db_session.flush()

    user = User(username="grace", email=None, hashed_password="hashed", role="admin", tenant_id=tenant.id)
    async_db_session.add(user)
    await async_db_session.flush()

    service = ApiConnectorService(tenant_id=tenant.id, db_session=async_db_session)
    connector = await service.create_connector(
        owner_id=user.id,
        name="retry-api",
        description=None,
        base_url="https://8.8.8.8",
        auth_type="none",
        auth_config={},
        rate_policy=RatePolicyDomain.from_raw(
            {
                "timeout_ms": 1000,
                "max_retries": 2,
                "retry_backoff_ms": 10,
                "retry_on_status": [503],
            }
        ),
        schema_source_type="manual",
        schema_source_url=None,
    )
    operation = await service.add_manual_operation_for_actor(
        connector_id=connector.id,
        actor=ActorContext(tenant_id=tenant.id, user_id=user.id, user_role=user.role),
        method="GET",
        path_template="/orders/{id}",
        operation_id="getOrder",
        summary="get order",
        description=None,
        tags=["orders"],
        request_schema={"type": "object"},
        response_schema={"type": "object"},
    )

    attempts = {"count": 0}
    slept: list[float] = []

    async def _fake_send(self, *, method, url, headers, query, body, timeout_ms):
        attempts["count"] += 1
        if attempts["count"] == 1:
            return 503, {}, {"ok": False}
        return 200, {"content-type": "application/json"}, {"ok": True}

    async def _fake_sleep(seconds: float):
        slept.append(seconds)

    monkeypatch.setattr(ApiConnectorExecutionService, "_send_http_request", _fake_send)
    monkeypatch.setattr("apps.shared.api_connector.execution.asyncio.sleep", _fake_sleep)

    exec_service = ApiConnectorExecutionService(tenant_id=tenant.id, db_session=async_db_session)
    result = await exec_service.execute_operation_for_actor(
        operation_uid=operation.operation_uid,
        actor=ActorContext(tenant_id=tenant.id, user_id=user.id, user_role=user.role),
        parameters=ApiOperationCallParameters(path={"id": "123"}),
    )

    assert result.status_code == 200
    assert attempts["count"] == 2
    assert len(slept) == 1


@pytest.mark.asyncio
async def test_rate_limiter_waits_when_tokens_exhausted(monkeypatch):
    exec_service = ApiConnectorExecutionService(tenant_id=1, db_session=object())

    class _RatePolicy:
        max_requests_per_second = 2.0

        @staticmethod
        def burst_size_value() -> int:
            return 1

    class _Connector:
        id = 1
        rate_policy = _RatePolicy()

    connector = _Connector()
    monotonics = iter([0.0, 0.0, 0.0, 0.5])
    slept: list[float] = []

    monkeypatch.setattr("apps.shared.api_connector.execution.monotonic", lambda: next(monotonics))

    async def _fake_sleep(seconds: float):
        slept.append(seconds)

    monkeypatch.setattr("apps.shared.api_connector.execution.asyncio.sleep", _fake_sleep)

    await exec_service._apply_rate_limit(connector)
    await exec_service._apply_rate_limit(connector)

    assert len(slept) == 1
    assert slept[0] > 0


@pytest.mark.asyncio
async def test_execute_operation_rejects_disabled_operation(async_db_session):
    tenant = Tenant(name="tenant_api_exec_disabled", slug="tenant_api_exec_disabled", config=None)
    async_db_session.add(tenant)
    await async_db_session.flush()

    user = User(username="irene", email=None, hashed_password="hashed", role="admin", tenant_id=tenant.id)
    async_db_session.add(user)
    await async_db_session.flush()

    service = ApiConnectorService(tenant_id=tenant.id, db_session=async_db_session)
    connector = await service.create_connector(
        owner_id=user.id,
        name="exec-disabled-api",
        description=None,
        base_url="https://8.8.8.8",
        auth_type="none",
        auth_config={},
        rate_policy=RatePolicyDomain.from_raw({}),
        schema_source_type="manual",
        schema_source_url=None,
    )
    operation = await service.add_manual_operation_for_actor(
        connector_id=connector.id,
        actor=ActorContext(tenant_id=tenant.id, user_id=user.id, user_role=user.role),
        method="GET",
        path_template="/orders/{id}",
        operation_id="getOrder",
        summary="get order",
        description=None,
        tags=["orders"],
        request_schema={"type": "object"},
        response_schema={"type": "object"},
    )

    await service.update_operation_status_for_actor(
        operation_id=operation.id,
        actor=ActorContext(tenant_id=tenant.id, user_id=user.id, user_role=user.role),
        status="disabled",
    )

    exec_service = ApiConnectorExecutionService(tenant_id=tenant.id, db_session=async_db_session)
    with pytest.raises(ResourceNotFoundError, match="Api operation not found"):
        await exec_service.execute_operation_for_actor(
            operation_uid=operation.operation_uid,
            actor=ActorContext(tenant_id=tenant.id, user_id=user.id, user_role=user.role),
            parameters=ApiOperationCallParameters(path={"id": "1"}),
        )
