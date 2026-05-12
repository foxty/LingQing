"""Integration tests for API connector schema sync dedup behavior."""

from datetime import UTC, datetime

import pytest

from apps.shared.api_connector.domain import RatePolicyDomain
from apps.shared.api_connector.service import ApiConnectorService
from apps.shared.db.models import Tenant, User
from apps.shared.domain.actor import ActorContext


@pytest.mark.asyncio
async def test_sync_deduplicates_by_method_and_path(async_db_session):
    tenant = Tenant(name="tenant_api_connector_it_1", slug="tenant_api_connector_it_1", config=None)
    async_db_session.add(tenant)
    await async_db_session.flush()

    user = User(username="it_admin", email=None, hashed_password="hashed", role="admin", tenant_id=tenant.id)
    async_db_session.add(user)
    await async_db_session.flush()

    service = ApiConnectorService(tenant_id=tenant.id, db_session=async_db_session)
    connector = await service.create_connector(
        owner_id=user.id,
        name="it-orders-api",
        description=None,
        base_url="https://8.8.8.8",
        auth_type="none",
        auth_config={},
        rate_policy=RatePolicyDomain.from_raw({}),
        schema_source_type="openapi_upload",
        schema_source_url=None,
    )

    openapi_v1 = """
openapi: 3.0.0
info:
  title: Orders API
  version: 1.0.0
paths:
  /orders/{id}:
    get:
      operationId: getOrderV1
      summary: get order
      responses:
        '200':
          description: ok
""".strip()

    summary_v1 = await service.sync_operations_from_schema_for_actor(
        connector_id=connector.id,
        actor=ActorContext(tenant_id=tenant.id, user_id=user.id, user_role=user.role),
        file_content=openapi_v1,
    )

    openapi_v2 = """
openapi: 3.0.0
info:
  title: Orders API
  version: 1.0.1
paths:
  /orders/{id}:
    get:
      operationId: getOrderV2
      summary: get order updated
      responses:
        '200':
          description: ok
""".strip()

    summary_v2 = await service.sync_operations_from_schema_for_actor(
        connector_id=connector.id,
        actor=ActorContext(tenant_id=tenant.id, user_id=user.id, user_role=user.role),
        file_content=openapi_v2,
    )

    rows, pagination = await service.list_operations_for_actor(
        connector_id=connector.id,
        actor=ActorContext(tenant_id=tenant.id, user_id=user.id, user_role=user.role),
    )
    imported_rows = [row for row in rows if row.source == "imported"]

    assert summary_v1.added == 1
    assert summary_v2.added == 0
    assert summary_v2.updated == 1
    assert summary_v2.staled == 0
    assert pagination.total == 1
    assert len(imported_rows) == 1
    assert imported_rows[0].method == "GET"
    assert imported_rows[0].path_template == "/orders/{id}"
    assert imported_rows[0].operation_id == "getOrderV2"


@pytest.mark.asyncio
async def test_search_operations_matches_operation_id(async_db_session):
    tenant = Tenant(name="tenant_api_connector_it_2", slug="tenant_api_connector_it_2", config=None)
    async_db_session.add(tenant)
    await async_db_session.flush()

    user = User(username="it_search_admin", email=None, hashed_password="hashed", role="admin", tenant_id=tenant.id)
    async_db_session.add(user)
    await async_db_session.flush()

    service = ApiConnectorService(tenant_id=tenant.id, db_session=async_db_session)
    connector = await service.create_connector(
        owner_id=user.id,
        name="it-search-api",
        description=None,
        base_url="https://8.8.8.8",
        auth_type="none",
        auth_config={},
        rate_policy=RatePolicyDomain.from_raw({}),
        schema_source_type="manual",
        schema_source_url=None,
    )

    await service.add_manual_operation_for_actor(
        connector_id=connector.id,
        actor=ActorContext(tenant_id=tenant.id, user_id=user.id, user_role=user.role),
        method="GET",
        path_template="/orders/{id}",
        operation_id="getOrderById",
        summary="",
        description=None,
        tags=[],
        request_schema={"type": "object"},
        response_schema={"type": "object"},
    )

    rows, pagination = await service.search_operations_for_actor(
        query="getOrderById",
        actor=ActorContext(tenant_id=tenant.id, user_id=user.id, user_role=user.role),
        connector_id=connector.id,
    )

    assert pagination.total == 1
    assert len(rows) == 1
    assert rows[0].operation_id == "getOrderById"


@pytest.mark.asyncio
async def test_operation_search_respects_scoped_connector_ids(async_db_session):
    tenant = Tenant(name="tenant_api_connector_it_3", slug="tenant_api_connector_it_3", config=None)
    async_db_session.add(tenant)
    await async_db_session.flush()

    user = User(username="it_scope_admin", email=None, hashed_password="hashed", role="admin", tenant_id=tenant.id)
    async_db_session.add(user)
    await async_db_session.flush()

    service = ApiConnectorService(tenant_id=tenant.id, db_session=async_db_session)
    connector_a = await service.create_connector(
        owner_id=user.id,
        name="it-scope-a",
        description=None,
        base_url="https://8.8.8.8",
        auth_type="none",
        auth_config={},
        rate_policy=RatePolicyDomain.from_raw({}),
        schema_source_type="manual",
        schema_source_url=None,
    )
    connector_b = await service.create_connector(
        owner_id=user.id,
        name="it-scope-b",
        description=None,
        base_url="https://8.8.8.8",
        auth_type="none",
        auth_config={},
        rate_policy=RatePolicyDomain.from_raw({}),
        schema_source_type="manual",
        schema_source_url=None,
    )

    await service.add_manual_operation_for_actor(
        connector_id=connector_a.id,
        actor=ActorContext(tenant_id=tenant.id, user_id=user.id, user_role=user.role),
        method="GET",
        path_template="/orders/a/{id}",
        operation_id="alpha_operation",
        summary="alpha order lookup",
        description=None,
        tags=[],
        request_schema={"type": "object"},
        response_schema={"type": "object"},
    )
    await service.add_manual_operation_for_actor(
        connector_id=connector_b.id,
        actor=ActorContext(tenant_id=tenant.id, user_id=user.id, user_role=user.role),
        method="GET",
        path_template="/orders/b/{id}",
        operation_id="beta_operation",
        summary="beta order lookup",
        description=None,
        tags=[],
        request_schema={"type": "object"},
        response_schema={"type": "object"},
    )

    rows = await service.operation_repo.search(
        tenant_id=tenant.id,
        query="order lookup",
        scoped_connector_ids=[connector_a.id],
        limit=20,
    )

    assert len(rows) == 1
    assert rows[0].connector_id == connector_a.id


@pytest.mark.asyncio
async def test_operation_search_returns_empty_when_connector_id_outside_scope(async_db_session):
    tenant = Tenant(name="tenant_api_connector_it_4", slug="tenant_api_connector_it_4", config=None)
    async_db_session.add(tenant)
    await async_db_session.flush()

    user = User(username="it_scope_guard", email=None, hashed_password="hashed", role="admin", tenant_id=tenant.id)
    async_db_session.add(user)
    await async_db_session.flush()

    service = ApiConnectorService(tenant_id=tenant.id, db_session=async_db_session)
    connector_a = await service.create_connector(
        owner_id=user.id,
        name="it-guard-a",
        description=None,
        base_url="https://8.8.8.8",
        auth_type="none",
        auth_config={},
        rate_policy=RatePolicyDomain.from_raw({}),
        schema_source_type="manual",
        schema_source_url=None,
    )
    connector_b = await service.create_connector(
        owner_id=user.id,
        name="it-guard-b",
        description=None,
        base_url="https://8.8.8.8",
        auth_type="none",
        auth_config={},
        rate_policy=RatePolicyDomain.from_raw({}),
        schema_source_type="manual",
        schema_source_url=None,
    )

    await service.add_manual_operation_for_actor(
        connector_id=connector_b.id,
        actor=ActorContext(tenant_id=tenant.id, user_id=user.id, user_role=user.role),
        method="GET",
        path_template="/orders/guard/{id}",
        operation_id="guard_operation",
        summary="guard order lookup",
        description=None,
        tags=[],
        request_schema={"type": "object"},
        response_schema={"type": "object"},
    )

    rows = await service.operation_repo.search(
        tenant_id=tenant.id,
        query="guard",
        connector_id=connector_b.id,
        scoped_connector_ids=[connector_a.id],
        limit=20,
    )

    assert rows == []


@pytest.mark.asyncio
async def test_operation_search_is_tenant_isolated(async_db_session):
    tenant_a = Tenant(name="tenant_api_connector_it_5a", slug="tenant_api_connector_it_5a", config=None)
    tenant_b = Tenant(name="tenant_api_connector_it_5b", slug="tenant_api_connector_it_5b", config=None)
    async_db_session.add_all([tenant_a, tenant_b])
    await async_db_session.flush()

    user_a = User(username="it_tenant_a", email=None, hashed_password="hashed", role="admin", tenant_id=tenant_a.id)
    user_b = User(username="it_tenant_b", email=None, hashed_password="hashed", role="admin", tenant_id=tenant_b.id)
    async_db_session.add_all([user_a, user_b])
    await async_db_session.flush()

    service_a = ApiConnectorService(tenant_id=tenant_a.id, db_session=async_db_session)
    service_b = ApiConnectorService(tenant_id=tenant_b.id, db_session=async_db_session)

    connector_a = await service_a.create_connector(
        owner_id=user_a.id,
        name="it-tenant-a",
        description=None,
        base_url="https://8.8.8.8",
        auth_type="none",
        auth_config={},
        rate_policy=RatePolicyDomain.from_raw({}),
        schema_source_type="manual",
        schema_source_url=None,
    )
    connector_b = await service_b.create_connector(
        owner_id=user_b.id,
        name="it-tenant-b",
        description=None,
        base_url="https://8.8.8.8",
        auth_type="none",
        auth_config={},
        rate_policy=RatePolicyDomain.from_raw({}),
        schema_source_type="manual",
        schema_source_url=None,
    )

    await service_a.add_manual_operation_for_actor(
        connector_id=connector_a.id,
        actor=ActorContext(tenant_id=tenant_a.id, user_id=user_a.id, user_role=user_a.role),
        method="GET",
        path_template="/orders/a/{id}",
        operation_id="shared_keyword_alpha",
        summary="shared keyword alpha",
        description=None,
        tags=[],
        request_schema={"type": "object"},
        response_schema={"type": "object"},
    )
    await service_b.add_manual_operation_for_actor(
        connector_id=connector_b.id,
        actor=ActorContext(tenant_id=tenant_b.id, user_id=user_b.id, user_role=user_b.role),
        method="GET",
        path_template="/orders/b/{id}",
        operation_id="shared_keyword_beta",
        summary="shared keyword beta",
        description=None,
        tags=[],
        request_schema={"type": "object"},
        response_schema={"type": "object"},
    )

    rows_a = await service_a.operation_repo.search(
        tenant_id=tenant_a.id,
        query="shared keyword",
        limit=20,
    )
    rows_b = await service_b.operation_repo.search(
        tenant_id=tenant_b.id,
        query="shared keyword",
        limit=20,
    )

    assert len(rows_a) == 1
    assert len(rows_b) == 1
    assert rows_a[0].tenant_id == tenant_a.id
    assert rows_b[0].tenant_id == tenant_b.id


@pytest.mark.asyncio
async def test_stream_operations_updated_since_filters_by_sync_status(async_db_session):
    tenant = Tenant(name="tenant_api_connector_it_6", slug="tenant_api_connector_it_6", config=None)
    async_db_session.add(tenant)
    await async_db_session.flush()

    user = User(username="it_sync_filter", email=None, hashed_password="hashed", role="admin", tenant_id=tenant.id)
    async_db_session.add(user)
    await async_db_session.flush()

    service = ApiConnectorService(tenant_id=tenant.id, db_session=async_db_session)
    connector = await service.create_connector(
        owner_id=user.id,
        name="it-sync-filter-api",
        description=None,
        base_url="https://8.8.8.8",
        auth_type="none",
        auth_config={},
        rate_policy=RatePolicyDomain.from_raw({}),
        schema_source_type="manual",
        schema_source_url=None,
    )

    op_never_synced = await service.add_manual_operation_for_actor(
        connector_id=connector.id,
        actor=ActorContext(tenant_id=tenant.id, user_id=user.id, user_role=user.role),
        method="GET",
        path_template="/sync/never/{id}",
        operation_id="op_never_synced",
        summary="never synced",
        description=None,
        tags=[],
        request_schema={"type": "object"},
        response_schema={"type": "object"},
    )
    op_with_error = await service.add_manual_operation_for_actor(
        connector_id=connector.id,
        actor=ActorContext(tenant_id=tenant.id, user_id=user.id, user_role=user.role),
        method="GET",
        path_template="/sync/error/{id}",
        operation_id="op_with_error",
        summary="with error",
        description=None,
        tags=[],
        request_schema={"type": "object"},
        response_schema={"type": "object"},
    )
    op_hash_mismatch = await service.add_manual_operation_for_actor(
        connector_id=connector.id,
        actor=ActorContext(tenant_id=tenant.id, user_id=user.id, user_role=user.role),
        method="GET",
        path_template="/sync/mismatch/{id}",
        operation_id="op_hash_mismatch",
        summary="hash mismatch",
        description=None,
        tags=[],
        request_schema={"type": "object"},
        response_schema={"type": "object"},
    )
    op_updated_only = await service.add_manual_operation_for_actor(
        connector_id=connector.id,
        actor=ActorContext(tenant_id=tenant.id, user_id=user.id, user_role=user.role),
        method="GET",
        path_template="/sync/updated/{id}",
        operation_id="op_updated_only",
        summary="updated only",
        description=None,
        tags=[],
        request_schema={"type": "object"},
        response_schema={"type": "object"},
    )
    op_clean = await service.add_manual_operation_for_actor(
        connector_id=connector.id,
        actor=ActorContext(tenant_id=tenant.id, user_id=user.id, user_role=user.role),
        method="GET",
        path_template="/sync/clean/{id}",
        operation_id="op_clean",
        summary="clean",
        description=None,
        tags=[],
        request_schema={"type": "object"},
        response_schema={"type": "object"},
    )

    now = datetime.now(UTC)

    row_never = await service.operation_repo.get_by_id_and_tenant(op_never_synced.id, tenant.id)
    assert row_never is not None
    row_never.last_vector_sync_error = None
    row_never.indexed_content_hash = None
    await service.operation_repo.update(row_never)

    row_error = await service.operation_repo.get_by_id_and_tenant(op_with_error.id, tenant.id)
    assert row_error is not None
    row_error.last_vector_synced_at = now
    row_error.last_vector_sync_error = "retry needed"
    await service.operation_repo.update(row_error)

    row_mismatch = await service.operation_repo.get_by_id_and_tenant(op_hash_mismatch.id, tenant.id)
    assert row_mismatch is not None
    row_mismatch.last_vector_sync_error = None
    row_mismatch.indexed_content_hash = "hash_mismatch"
    await service.operation_repo.update(row_mismatch)

    row_updated_only = await service.operation_repo.get_by_id_and_tenant(op_updated_only.id, tenant.id)
    assert row_updated_only is not None
    row_updated_only.last_vector_synced_at = now
    row_updated_only.last_vector_sync_error = None
    row_updated_only.indexed_content_hash = row_updated_only.content_hash
    row_updated_only.updated_at = now
    await service.operation_repo.update(row_updated_only)

    row_clean = await service.operation_repo.get_by_id_and_tenant(op_clean.id, tenant.id)
    assert row_clean is not None
    row_clean.last_vector_synced_at = now
    row_clean.last_vector_sync_error = None
    row_clean.indexed_content_hash = row_clean.content_hash
    row_clean.updated_at = now
    await service.operation_repo.update(row_clean)
