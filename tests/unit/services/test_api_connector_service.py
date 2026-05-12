"""Unit tests for ApiConnectorService."""

from unittest.mock import MagicMock, patch

import pytest

from apps.shared.api_connector.domain import RatePolicyDomain
from apps.shared.api_connector.schemas import NoAuthConfigSchema
from apps.shared.api_connector.service import ApiConnectorService
from apps.shared.core.exceptions import ResourceNotFoundError, ValidationError
from apps.shared.db.models import Tenant, User
from apps.shared.domain.actor import ActorContext


async def _mock_upsert_noop(_payload):
    """Async mock for upsert_payload."""
    return 1


@pytest.fixture
def mock_rag_indexing_service():
    """Create a mock ResourceIndexService to avoid ChromaDB connection."""
    mock = MagicMock()
    mock.rag_manager = MagicMock()
    mock.upsert_payload = _mock_upsert_noop
    return mock


@pytest.mark.asyncio
async def test_create_connector_encrypts_sensitive_fields(async_db_session, mock_rag_indexing_service):
    """Test that create_connector returns masked auth_config in response DTO."""
    tenant = Tenant(name="tenant_api_connector_1", slug="tenant_api_connector_1", config=None)
    async_db_session.add(tenant)
    await async_db_session.flush()

    user = User(username="alice", email=None, hashed_password="hashed", role="admin", tenant_id=tenant.id)
    async_db_session.add(user)
    await async_db_session.flush()

    with patch("apps.shared.search.indexing_service.ResourceIndexService", return_value=mock_rag_indexing_service):
        service = ApiConnectorService(tenant_id=tenant.id, db_session=async_db_session)
        created = await service.create_connector(
            owner_id=user.id,
            name="crm-api",
            description="CRM APIs",
            base_url="https://8.8.8.8",
            auth_type="api_key",
            auth_config={"key_name": "X-API-Key", "key_value": "secret-token"},
            rate_policy=RatePolicyDomain.from_raw({"timeout_ms": 20000}),
            schema_source_type="manual",
            schema_source_url=None,
        )

    # Service returns response DTO with masked auth_config
    assert created.id is not None
    # auth_config_masked should contain the masked value (not encrypted, not plaintext)
    assert "auth_config_masked" in created.model_dump()
    assert created.auth_config_masked["key_value"].startswith("se")  # First 2 chars visible
    assert created.auth_config_masked["key_value"].endswith("en")  # Last 2 chars visible
    assert "*" in created.auth_config_masked["key_value"]  # Middle is masked
    assert created.auth_config_masked["key_value"] != "secret-token"  # Not plaintext


@pytest.mark.asyncio
async def test_create_connector_accepts_pydantic_no_auth_schema(async_db_session, mock_rag_indexing_service):
    """HTTP create parses auth_config as NoAuthConfigSchema; persist must JSON-serialize it."""
    tenant = Tenant(name="tenant_api_connector_none_auth", slug="tenant_api_connector_none_auth", config=None)
    async_db_session.add(tenant)
    await async_db_session.flush()

    user = User(username="alice", email=None, hashed_password="hashed", role="admin", tenant_id=tenant.id)
    async_db_session.add(user)
    await async_db_session.flush()

    with patch("apps.shared.search.indexing_service.ResourceIndexService", return_value=mock_rag_indexing_service):
        service = ApiConnectorService(tenant_id=tenant.id, db_session=async_db_session)
        created = await service.create_connector(
            owner_id=user.id,
            name="public-api",
            description="adsfasfa",
            base_url="https://example.com",
            auth_type="none",
            auth_config=NoAuthConfigSchema(),
            rate_policy=RatePolicyDomain.from_raw({}),
            schema_source_type="manual",
            schema_source_url=None,
        )

    assert created.id is not None
    assert created.auth_type == "none"
    assert created.auth_config_masked["auth_method"] == "none"


@pytest.mark.asyncio
async def test_get_connector_for_actor_includes_owner_name(async_db_session, mock_rag_indexing_service):
    tenant = Tenant(name="tenant_api_connector_owner", slug="tenant_api_connector_owner", config=None)
    async_db_session.add(tenant)
    await async_db_session.flush()

    user = User(username="owner-user", email=None, hashed_password="hashed", role="admin", tenant_id=tenant.id)
    async_db_session.add(user)
    await async_db_session.flush()

    with patch("apps.shared.search.indexing_service.ResourceIndexService", return_value=mock_rag_indexing_service):
        service = ApiConnectorService(tenant_id=tenant.id, db_session=async_db_session)
        created = await service.create_connector(
            owner_id=user.id,
            name="owner-api",
            description="with owner",
            base_url="https://8.8.8.8",
            auth_type="none",
            auth_config={},
            rate_policy=RatePolicyDomain.from_raw({}),
            schema_source_type="manual",
            schema_source_url=None,
        )

        fetched = await service.get_connector_for_actor(
            connector_id=created.id,
            actor=ActorContext(tenant_id=tenant.id, user_id=user.id, user_role=user.role),
        )

    assert fetched.owner_name == "owner-user"


@pytest.mark.asyncio
async def test_sync_operations_from_openapi_upload_creates_index_rows(async_db_session, mock_rag_indexing_service):
    tenant = Tenant(name="tenant_api_connector_2", slug="tenant_api_connector_2", config=None)
    async_db_session.add(tenant)
    await async_db_session.flush()

    user = User(username="bob", email=None, hashed_password="hashed", role="admin", tenant_id=tenant.id)
    async_db_session.add(user)
    await async_db_session.flush()

    with patch("apps.shared.search.indexing_service.ResourceIndexService", return_value=mock_rag_indexing_service):
        service = ApiConnectorService(tenant_id=tenant.id, db_session=async_db_session)
        connector = await service.create_connector(
            owner_id=user.id,
            name="orders-api",
            description=None,
            base_url="https://8.8.8.8",
            auth_type="none",
            auth_config={},
            rate_policy=RatePolicyDomain.from_raw({}),
            schema_source_type="openapi_upload",
            schema_source_url=None,
        )

        openapi = """
openapi: 3.0.0
info:
  title: Orders API
  version: 1.0.0
paths:
  /orders:
    get:
      summary: list orders
      operationId: listOrders
      responses:
        '200':
          description: ok
  /orders/{id}:
    get:
      summary: get order
      operationId: getOrder
      parameters:
        - in: path
          name: id
          required: true
          schema:
            type: string
      responses:
        '200':
          description: ok
""".strip()

        summary = await service.sync_operations_from_schema_for_actor(
            connector_id=connector.id,
            actor=ActorContext(tenant_id=tenant.id, user_id=user.id, user_role=user.role),
            file_content=openapi,
        )
        rows, pagination = await service.list_operations_for_actor(
            connector_id=connector.id,
            actor=ActorContext(tenant_id=tenant.id, user_id=user.id, user_role=user.role),
        )

    assert summary.added == 2
    assert summary.updated == 0
    assert summary.staled == 0
    assert pagination.total == 2
    assert len(rows) == 2
    assert any(row.operation_id == "listOrders" for row in rows)


@pytest.mark.asyncio
async def test_add_manual_operation_rejects_invalid_method(async_db_session, mock_rag_indexing_service):
    tenant = Tenant(name="tenant_api_connector_3", slug="tenant_api_connector_3", config=None)
    async_db_session.add(tenant)
    await async_db_session.flush()

    user = User(username="charlie", email=None, hashed_password="hashed", role="admin", tenant_id=tenant.id)
    async_db_session.add(user)
    await async_db_session.flush()

    with patch("apps.shared.search.indexing_service.ResourceIndexService", return_value=mock_rag_indexing_service):
        service = ApiConnectorService(tenant_id=tenant.id, db_session=async_db_session)
        connector = await service.create_connector(
            owner_id=user.id,
            name="manual-api",
            description=None,
            base_url="https://8.8.8.8",
            auth_type="none",
            auth_config={},
            rate_policy=RatePolicyDomain.from_raw({}),
            schema_source_type="manual",
            schema_source_url=None,
        )

        with pytest.raises(ValidationError, match="Unsupported method"):
            await service.add_manual_operation_for_actor(
                connector_id=connector.id,
                actor=ActorContext(tenant_id=tenant.id, user_id=user.id, user_role=user.role),
                method="TRACE",
                path_template="/x",
                operation_id=None,
                summary="bad",
                description=None,
                tags=[],
                request_schema={"type": "object"},
                response_schema={"type": "object"},
            )


@pytest.mark.asyncio
async def test_sync_keeps_disabled_imported_and_manual_operations(async_db_session, mock_rag_indexing_service):
    tenant = Tenant(name="tenant_api_connector_5", slug="tenant_api_connector_5", config=None)
    async_db_session.add(tenant)
    await async_db_session.flush()

    user = User(username="erin", email=None, hashed_password="hashed", role="admin", tenant_id=tenant.id)
    async_db_session.add(user)
    await async_db_session.flush()

    with patch("apps.shared.search.indexing_service.ResourceIndexService", return_value=mock_rag_indexing_service):
        service = ApiConnectorService(tenant_id=tenant.id, db_session=async_db_session)
        connector = await service.create_connector(
            owner_id=user.id,
            name="mixed-api",
            description=None,
            base_url="https://8.8.8.8",
            auth_type="none",
            auth_config={},
            rate_policy=RatePolicyDomain.from_raw({}),
            schema_source_type="openapi_upload",
            schema_source_url=None,
        )

        imported_openapi = """
openapi: 3.0.0
info:
  title: Orders API
  version: 1.0.0
paths:
  /orders/{id}:
    get:
      operationId: getOrder
      summary: get order
      responses:
        '200':
          description: ok
""".strip()

        await service.sync_operations_from_schema_for_actor(
            connector_id=connector.id,
            actor=ActorContext(tenant_id=tenant.id, user_id=user.id, user_role=user.role),
            file_content=imported_openapi,
        )
        rows, _ = await service.list_operations_for_actor(
            connector_id=connector.id,
            actor=ActorContext(tenant_id=tenant.id, user_id=user.id, user_role=user.role),
        )
        imported = next(row for row in rows if row.source == "imported")

        await service.update_operation_status_for_actor(
            operation_id=imported.id,
            actor=ActorContext(tenant_id=tenant.id, user_id=user.id, user_role=user.role),
            status="disabled",
        )

        await service.add_manual_operation_for_actor(
            connector_id=connector.id,
            actor=ActorContext(tenant_id=tenant.id, user_id=user.id, user_role=user.role),
            method="GET",
            path_template="/orders/manual/{id}",
            operation_id="manualOrder",
            summary="manual order",
            description=None,
            tags=["manual"],
            request_schema={"type": "object"},
            response_schema={"type": "object"},
        )

        imported_openapi_v2 = """
openapi: 3.0.0
info:
  title: Orders API
  version: 1.0.1
paths:
  /orders/{id}:
    get:
      operationId: getOrder
      summary: get order updated
      responses:
        '200':
          description: ok
""".strip()

        await service.sync_operations_from_schema_for_actor(
            connector_id=connector.id,
            actor=ActorContext(tenant_id=tenant.id, user_id=user.id, user_role=user.role),
            file_content=imported_openapi_v2,
        )

        rows, _ = await service.list_operations_for_actor(
            connector_id=connector.id,
            actor=ActorContext(tenant_id=tenant.id, user_id=user.id, user_role=user.role),
        )
        imported_after = next(row for row in rows if row.source == "imported")
        manual_after = next(row for row in rows if row.source == "manual")

    assert imported_after.status == "disabled"
    assert imported_after.summary == "get order updated"
    assert manual_after.operation_id == "manualOrder"


@pytest.mark.asyncio
async def test_sync_operations_returns_updated_staled_and_unchanged_counts(async_db_session, mock_rag_indexing_service):
    tenant = Tenant(name="tenant_api_connector_6", slug="tenant_api_connector_6", config=None)
    async_db_session.add(tenant)
    await async_db_session.flush()

    user = User(username="fiona", email=None, hashed_password="hashed", role="admin", tenant_id=tenant.id)
    async_db_session.add(user)
    await async_db_session.flush()

    with patch("apps.shared.search.indexing_service.ResourceIndexService", return_value=mock_rag_indexing_service):
        service = ApiConnectorService(tenant_id=tenant.id, db_session=async_db_session)
        connector = await service.create_connector(
            owner_id=user.id,
            name="diff-api",
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
  title: Diff API
  version: 1.0.0
paths:
  /orders/{id}:
    get:
      operationId: getOrder
      summary: get order
      responses:
        '200':
          description: ok
  /customers/{id}:
    get:
      operationId: getCustomer
      summary: get customer
      responses:
        '200':
          description: ok
""".strip()

        await service.sync_operations_from_schema_for_actor(
            connector_id=connector.id,
            actor=ActorContext(tenant_id=tenant.id, user_id=user.id, user_role=user.role),
            file_content=openapi_v1,
        )

        openapi_v2 = """
openapi: 3.0.0
info:
  title: Diff API
  version: 1.0.1
paths:
  /orders/{id}:
    get:
      operationId: getOrder
      summary: get order updated
      responses:
        '200':
          description: ok
  /invoices/{id}:
    get:
      operationId: getInvoice
      summary: get invoice
      responses:
        '200':
          description: ok
""".strip()

        summary = await service.sync_operations_from_schema_for_actor(
            connector_id=connector.id,
            actor=ActorContext(tenant_id=tenant.id, user_id=user.id, user_role=user.role),
            file_content=openapi_v2,
        )

    assert summary.added == 1
    assert summary.updated == 1
    assert summary.staled == 1
    assert summary.unchanged == 0


@pytest.mark.asyncio
async def test_sync_uses_method_and_path_as_identity_when_operation_id_changes(
    async_db_session, mock_rag_indexing_service
):
    tenant = Tenant(name="tenant_api_connector_8", slug="tenant_api_connector_8", config=None)
    async_db_session.add(tenant)
    await async_db_session.flush()

    user = User(username="ivy", email=None, hashed_password="hashed", role="admin", tenant_id=tenant.id)
    async_db_session.add(user)
    await async_db_session.flush()

    with patch("apps.shared.search.indexing_service.ResourceIndexService", return_value=mock_rag_indexing_service):
        service = ApiConnectorService(tenant_id=tenant.id, db_session=async_db_session)
        connector = await service.create_connector(
            owner_id=user.id,
            name="identity-api",
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
  title: Identity API
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
  title: Identity API
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

        rows, _ = await service.list_operations_for_actor(
            connector_id=connector.id,
            actor=ActorContext(tenant_id=tenant.id, user_id=user.id, user_role=user.role),
        )
        imported_rows = [row for row in rows if row.source == "imported"]

    assert summary_v1.added == 1
    assert summary_v2.added == 0
    assert summary_v2.updated == 1
    assert summary_v2.staled == 0
    assert len(imported_rows) == 1
    assert imported_rows[0].operation_id == "getOrderV2"
    assert imported_rows[0].summary == "get order updated"


@pytest.mark.asyncio
async def test_sync_treats_same_path_with_different_methods_as_distinct(async_db_session, mock_rag_indexing_service):
    tenant = Tenant(name="tenant_api_connector_9", slug="tenant_api_connector_9", config=None)
    async_db_session.add(tenant)
    await async_db_session.flush()

    user = User(username="jane", email=None, hashed_password="hashed", role="admin", tenant_id=tenant.id)
    async_db_session.add(user)
    await async_db_session.flush()

    with patch("apps.shared.search.indexing_service.ResourceIndexService", return_value=mock_rag_indexing_service):
        service = ApiConnectorService(tenant_id=tenant.id, db_session=async_db_session)
        connector = await service.create_connector(
            owner_id=user.id,
            name="method-api",
            description=None,
            base_url="https://8.8.8.8",
            auth_type="none",
            auth_config={},
            rate_policy=RatePolicyDomain.from_raw({}),
            schema_source_type="openapi_upload",
            schema_source_url=None,
        )

        openapi = """
openapi: 3.0.0
info:
  title: Method API
  version: 1.0.0
paths:
  /orders/{id}:
    get:
      operationId: getOrder
      summary: get order
      responses:
        '200':
          description: ok
    post:
      operationId: updateOrder
      summary: update order
      responses:
        '200':
          description: ok
""".strip()

        summary = await service.sync_operations_from_schema_for_actor(
            connector_id=connector.id,
            actor=ActorContext(tenant_id=tenant.id, user_id=user.id, user_role=user.role),
            file_content=openapi,
        )

        rows, _ = await service.list_operations_for_actor(
            connector_id=connector.id,
            actor=ActorContext(tenant_id=tenant.id, user_id=user.id, user_role=user.role),
        )
        imported_rows = [row for row in rows if row.source == "imported"]

    assert summary.added == 2
    assert len(imported_rows) == 2
    assert {(row.method, row.path_template) for row in imported_rows} == {
        ("GET", "/orders/{id}"),
        ("POST", "/orders/{id}"),
    }


@pytest.mark.asyncio
async def test_operation_update_delete_guard_and_status_validation(async_db_session, mock_rag_indexing_service):
    tenant = Tenant(name="tenant_api_connector_7", slug="tenant_api_connector_7", config=None)
    async_db_session.add(tenant)
    await async_db_session.flush()

    user = User(username="henry", email=None, hashed_password="hashed", role="admin", tenant_id=tenant.id)
    async_db_session.add(user)
    await async_db_session.flush()

    with patch("apps.shared.search.indexing_service.ResourceIndexService", return_value=mock_rag_indexing_service):
        service = ApiConnectorService(tenant_id=tenant.id, db_session=async_db_session)
        connector = await service.create_connector(
            owner_id=user.id,
            name="guard-api",
            description=None,
            base_url="https://8.8.8.8",
            auth_type="none",
            auth_config={},
            rate_policy=RatePolicyDomain.from_raw({}),
            schema_source_type="openapi_upload",
            schema_source_url=None,
        )

        imported_openapi = """
openapi: 3.0.0
info:
  title: Guard API
  version: 1.0.0
paths:
  /orders/{id}:
    get:
      operationId: getOrder
      summary: get order
      responses:
        '200':
          description: ok
""".strip()

        await service.sync_operations_from_schema_for_actor(
            connector_id=connector.id,
            actor=ActorContext(tenant_id=tenant.id, user_id=user.id, user_role=user.role),
            file_content=imported_openapi,
        )

        manual = await service.add_manual_operation_for_actor(
            connector_id=connector.id,
            actor=ActorContext(tenant_id=tenant.id, user_id=user.id, user_role=user.role),
            method="GET",
            path_template="/orders/manual/{id}",
            operation_id="manualOrder",
            summary="manual order",
            description=None,
            tags=[],
            request_schema={"type": "object"},
            response_schema={"type": "object"},
        )

        rows, _ = await service.list_operations_for_actor(
            connector_id=connector.id,
            actor=ActorContext(tenant_id=tenant.id, user_id=user.id, user_role=user.role),
        )
        imported = next(row for row in rows if row.source == "imported")

        with pytest.raises(ValidationError, match="cannot be edited"):
            await service.update_operation_for_actor(
                operation_id=imported.id,
                actor=ActorContext(tenant_id=tenant.id, user_id=user.id, user_role=user.role),
                summary="blocked",
            )

        with pytest.raises(ValidationError, match="cannot be deleted"):
            await service.delete_operation_for_actor(
                operation_id=imported.id,
                actor=ActorContext(tenant_id=tenant.id, user_id=user.id, user_role=user.role),
            )

        updated_manual = await service.update_operation_for_actor(
            operation_id=manual.id,
            actor=ActorContext(tenant_id=tenant.id, user_id=user.id, user_role=user.role),
            summary="manual updated",
            method="POST",
        )
        assert updated_manual.summary == "manual updated"
        assert updated_manual.method == "POST"

        await service.delete_operation_for_actor(
            operation_id=manual.id,
            actor=ActorContext(tenant_id=tenant.id, user_id=user.id, user_role=user.role),
        )
        with pytest.raises(ResourceNotFoundError, match="Api operation not found"):
            await service.update_operation_for_actor(
                operation_id=manual.id,
                actor=ActorContext(tenant_id=tenant.id, user_id=user.id, user_role=user.role),
                summary="should fail",
            )

        with pytest.raises(ValidationError, match="Only active/disabled"):
            await service.update_operation_status_for_actor(
                operation_id=imported.id,
                actor=ActorContext(tenant_id=tenant.id, user_id=user.id, user_role=user.role),
                status="stale",
            )


@pytest.mark.asyncio
async def test_update_connector_preserves_original_secret_when_ui_sends_masked_value(
    async_db_session, mock_rag_indexing_service
):
    """Test that updating a connector with masked auth_config preserves original secrets.

    Scenario:
    1. Create connector with real secret "my-secret-key-12345"
    2. UI gets masked response: "my*************45"
    3. User updates connector name, UI sends back masked secret
    4. Service should detect masked value and preserve original secret
    5. Execution should still work with original secret
    """
    tenant = Tenant(name="tenant_masked_update", slug="tenant_masked_update", config=None)
    async_db_session.add(tenant)
    await async_db_session.flush()

    user = User(username="masked-user", email=None, hashed_password="hashed", role="admin", tenant_id=tenant.id)
    async_db_session.add(user)
    await async_db_session.flush()

    original_secret = "my-secret-key-12345"

    with patch("apps.shared.search.indexing_service.ResourceIndexService", return_value=mock_rag_indexing_service):
        service = ApiConnectorService(tenant_id=tenant.id, db_session=async_db_session)

        # Step 1: Create connector with real secret
        created = await service.create_connector(
            owner_id=user.id,
            name="kingdee-erp",
            description="Kingdee ERP Connector",
            base_url="https://erp.kingdee.com",
            auth_type="custom",
            auth_config={
                "auth_method": "custom",
                "login_endpoint": "/login",
                "login_payload_template": {"parameters": ["{username}", "{app_secret}"]},
                "token_extraction": {"session_id": "Context.SessionId"},
                "request_headers": {"Cookie": "kdservice-sessionid={session_id}"},
                "extra_config": {
                    "app_secret": original_secret,
                    "username": "admin",
                },
            },
            rate_policy=RatePolicyDomain.from_raw({}),
            schema_source_type="manual",
            schema_source_url=None,
        )

        # Step 2: UI receives masked value
        masked_secret = created.auth_config_masked["extra_config"]["app_secret"]
        assert masked_secret != original_secret
        assert "*" in masked_secret

        # Step 3: User updates name, UI sends back full auth_config with masked secret
        updated = await service.update_connector_for_actor(
            connector_id=created.id,
            actor=ActorContext(tenant_id=tenant.id, user_id=user.id, user_role=user.role),
            name="kingdee-erp-updated",
            auth_config={
                "auth_method": "custom",
                "login_endpoint": "/login",
                "login_payload_template": {"parameters": ["{username}", "{app_secret}"]},
                "token_extraction": {"session_id": "Context.SessionId"},
                "request_headers": {"Cookie": "kdservice-sessionid={session_id}"},
                "extra_config": {
                    "app_secret": masked_secret,  # UI sends masked value!
                    "username": "admin",
                },
            },
        )

        assert updated.name == "kingdee-erp-updated"

        # Step 4: Fetch connector and verify original secret is preserved
        fetched = await service.get_connector_for_actor(
            connector_id=created.id,
            actor=ActorContext(tenant_id=tenant.id, user_id=user.id, user_role=user.role),
        )

        # The masked value in response should still be the same pattern
        assert fetched.auth_config_masked["extra_config"]["app_secret"] == masked_secret

        # Step 5: Verify by executing (decrypt should get original, not masked)
        from apps.shared.api_connector.adapters import connector_entity_to_domain
        from apps.shared.api_connector.repository import ApiConnectorRepository

        repo = ApiConnectorRepository(async_db_session)
        entity = await repo.get_by_id_and_tenant(created.id, tenant.id)
        domain = connector_entity_to_domain(entity, cipher=service.cipher)

        # Domain should have the ORIGINAL secret, not the masked one
        assert domain.auth_config.extra_config["app_secret"] == original_secret
        assert domain.auth_config.extra_config["app_secret"] != masked_secret


@pytest.mark.asyncio
async def test_update_connector_allows_changing_secret_with_real_value(async_db_session, mock_rag_indexing_service):
    """Test that providing a real (non-masked) secret during update actually changes it."""
    tenant = Tenant(name="tenant_secret_change", slug="tenant_secret_change", config=None)
    async_db_session.add(tenant)
    await async_db_session.flush()

    user = User(username="change-user", email=None, hashed_password="hashed", role="admin", tenant_id=tenant.id)
    async_db_session.add(user)
    await async_db_session.flush()

    original_secret = "old-secret-key"
    new_secret = "new-secret-key-67890"

    with patch("apps.shared.search.indexing_service.ResourceIndexService", return_value=mock_rag_indexing_service):
        service = ApiConnectorService(tenant_id=tenant.id, db_session=async_db_session)

        # Create with old secret
        created = await service.create_connector(
            owner_id=user.id,
            name="test-api",
            description="Test API",
            base_url="https://api.test.com",
            auth_type="api_key",
            auth_config={"key_value": original_secret},
            rate_policy=RatePolicyDomain.from_raw({}),
            schema_source_type="manual",
            schema_source_url=None,
        )

        # Update with NEW real secret (not masked)
        updated = await service.update_connector_for_actor(
            connector_id=created.id,
            actor=ActorContext(tenant_id=tenant.id, user_id=user.id, user_role=user.role),
            auth_config={"key_value": new_secret},
        )

        # Verify the secret was actually changed
        from apps.shared.api_connector.adapters import connector_entity_to_domain
        from apps.shared.api_connector.repository import ApiConnectorRepository

        repo = ApiConnectorRepository(async_db_session)
        entity = await repo.get_by_id_and_tenant(created.id, tenant.id)
        domain = connector_entity_to_domain(entity, cipher=service.cipher)

        # Domain should have the NEW secret
        assert domain.auth_config.key_value == new_secret
        assert domain.auth_config.key_value != original_secret


@pytest.mark.asyncio
async def test_update_connector_mixed_masked_and_real_values(async_db_session, mock_rag_indexing_service):
    """Test updating with mix of masked (keep original) and real (update) values."""
    tenant = Tenant(name="tenant_mixed_update", slug="tenant_mixed_update", config=None)
    async_db_session.add(tenant)
    await async_db_session.flush()

    user = User(username="mixed-user", email=None, hashed_password="hashed", role="admin", tenant_id=tenant.id)
    async_db_session.add(user)
    await async_db_session.flush()

    with patch("apps.shared.search.indexing_service.ResourceIndexService", return_value=mock_rag_indexing_service):
        service = ApiConnectorService(tenant_id=tenant.id, db_session=async_db_session)

        # Create connector with multiple secrets
        created = await service.create_connector(
            owner_id=user.id,
            name="multi-secret-api",
            description="API with multiple secrets",
            base_url="https://api.example.com",
            auth_type="custom",
            auth_config={
                "auth_method": "custom",
                "login_endpoint": "/login",
                "login_payload_template": {"parameters": ["{username}", "{app_secret}"]},
                "token_extraction": {"session_id": "Context.SessionId"},
                "request_headers": {"Cookie": "kdservice-sessionid={session_id}"},
                "extra_config": {
                    "app_secret": "secret-to-keep",
                    "app_key": "key-to-change",
                    "username": "admin",
                },
            },
            rate_policy=RatePolicyDomain.from_raw({}),
            schema_source_type="manual",
            schema_source_url=None,
        )

        # Get masked values
        masked_secret = created.auth_config_masked["extra_config"]["app_secret"]
        assert "*" in masked_secret

        # Update: keep app_secret (masked), change app_key (real value)
        new_app_key = "new-key-value-xyz"
        updated = await service.update_connector_for_actor(
            connector_id=created.id,
            actor=ActorContext(tenant_id=tenant.id, user_id=user.id, user_role=user.role),
            auth_config={
                "auth_method": "custom",
                "login_endpoint": "/login",
                "login_payload_template": {"parameters": ["{username}", "{app_secret}"]},
                "token_extraction": {"session_id": "Context.SessionId"},
                "request_headers": {"Cookie": "kdservice-sessionid={session_id}"},
                "extra_config": {
                    "app_secret": masked_secret,  # Masked - should keep original
                    "app_key": new_app_key,  # Real value - should update
                    "username": "admin",
                },
            },
        )

        # Verify mixed behavior
        from apps.shared.api_connector.adapters import connector_entity_to_domain
        from apps.shared.api_connector.repository import ApiConnectorRepository

        repo = ApiConnectorRepository(async_db_session)
        entity = await repo.get_by_id_and_tenant(created.id, tenant.id)
        domain = connector_entity_to_domain(entity, cipher=service.cipher)

        # app_secret should be ORIGINAL (masked value was skipped)
        assert domain.auth_config.extra_config["app_secret"] == "secret-to-keep"

        # app_key should be NEW (real value was applied)
        assert domain.auth_config.extra_config["app_key"] == new_app_key

        # username should be UNCHANGED (same value)
        assert domain.auth_config.extra_config["username"] == "admin"
