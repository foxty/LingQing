"""Session-scoped application tests: pack install, re-install, and sync (uses DB fixture)."""

from pathlib import Path

import pytest

from apps.shared.core.exceptions import ValidationError
from apps.shared.db.models import ApiConnector, Tenant, User
from apps.shared.domain.actor import ActorContext
from apps.shared.external_systems.api_connector.constants import OPERATION_STATUS_STALE
from apps.shared.external_systems.api_connector.domain import RatePolicyDomain
from apps.shared.external_systems.api_connector.schemas import InstallPackOAuthInput
from apps.shared.external_systems.api_connector.service import ApiConnectorService
from apps.shared.external_systems.packs.loader import ApiConnectorPackCatalog
from apps.shared.external_systems.packs.versioning import build_pack_operation_upstream_key


async def _install_pack(
    service: ApiConnectorService,
    catalog: ApiConnectorPackCatalog,
    *,
    actor: ActorContext,
    pack_id: str,
    **oauth_fields,
):
    manifest = catalog.get(pack_id)
    return await service.install_integration_pack_for_actor(
        actor=actor,
        manifest=manifest,
        oauth=InstallPackOAuthInput(
            client_id=oauth_fields.get("client_id"),
            client_secret=oauth_fields.get("client_secret"),
            redirect_uri=oauth_fields.get("redirect_uri"),
        ),
    )


async def _sync_pack(
    service: ApiConnectorService,
    catalog: ApiConnectorPackCatalog,
    *,
    actor: ActorContext,
    connector_id: int,
):
    return await service.sync_installed_pack_for_connector_for_actor(
        actor=actor,
        connector_id=connector_id,
        catalog=catalog,
    )


async def _seed_tenant_admin(async_db_session, *, slug: str) -> tuple[Tenant, User, ActorContext]:
    tenant = Tenant(name=f"pack_{slug}", slug=slug, config=None)
    async_db_session.add(tenant)
    await async_db_session.flush()
    user = User(
        username=f"pack_admin_{slug}",
        email=None,
        hashed_password="synthetic",
        role="admin",
        tenant_id=tenant.id,
    )
    async_db_session.add(user)
    await async_db_session.flush()
    actor = ActorContext(tenant_id=tenant.id, user_id=user.id, user_role=user.role)
    return tenant, user, actor


@pytest.mark.asyncio
async def test_pack_install_is_idempotent(async_db_session, tmp_path: Path):
    (tmp_path / "test-pack.yaml").write_text(
        """
pack_id: test-api-user
version: 1.0.0
agent_instructions: Use focused searches and keep calls read-only.
connector:
  name: Test API User
  base_url: https://api.example.test
oauth:
  authorize_url: https://auth.example.test/authorize
  token_url: https://auth.example.test/token
  scopes:
    - read:basic
operations:
  - method: POST
    path: /items.search
    operation_id: test_search_items
    summary: Search synthetic items.
    request_schema: {type: object}
    response_schema: {type: object}
""",
        encoding="utf-8",
    )
    tenant, _user, actor = await _seed_tenant_admin(async_db_session, slug="test-pack-tenant")
    catalog = ApiConnectorPackCatalog(tmp_path)
    service = ApiConnectorService(tenant.id, async_db_session)
    created_connector, created_summary = await _install_pack(
        service,
        catalog,
        actor=actor,
        pack_id="test-api-user",
        client_id="synthetic-client",
        client_secret="synthetic-secret",
    )
    connector = await async_db_session.get(ApiConnector, created_connector.id)
    assert connector is not None
    assert created_summary.added == 1
    assert connector.installed_pack_version == "1.0.0"

    ops = await service.operation_repo.list_by_connector(tenant.id, created_connector.id)
    assert len(ops) == 1
    assert ops[0].upstream_key == build_pack_operation_upstream_key("test_search_items")

    connector.agent_instructions = "stale instructions"
    await async_db_session.flush()
    repeated_connector, repeated_summary = await _install_pack(service, catalog, actor=actor, pack_id="test-api-user")

    assert created_connector.id == repeated_connector.id
    assert repeated_connector.pack_ref == "test-api-user@1"
    assert repeated_connector.agent_instructions == "Use focused searches and keep calls read-only."
    assert repeated_connector.installed_pack_version == "1.0.0"
    assert repeated_summary is not None


@pytest.mark.asyncio
async def test_pack_reinstall_syncs_new_manifest_operations(async_db_session, tmp_path: Path):
    pack_path = tmp_path / "test-pack.yaml"
    pack_path.write_text(
        """
pack_id: test-api-user
version: 1.0.0
connector:
  name: Test API User
  base_url: https://api.example.test
oauth:
  authorize_url: https://auth.example.test/authorize
  token_url: https://auth.example.test/token
operations:
  - method: POST
    path: /items.search
    operation_id: test_search_items
    summary: Search synthetic items.
    request_schema: {type: object}
    response_schema: {type: object}
""",
        encoding="utf-8",
    )
    tenant, _user, actor = await _seed_tenant_admin(async_db_session, slug="test-pack-sync")
    catalog = ApiConnectorPackCatalog(tmp_path)
    service = ApiConnectorService(tenant.id, async_db_session)
    created_connector, _ = await _install_pack(
        service,
        catalog,
        actor=actor,
        pack_id="test-api-user",
        client_id="synthetic-client",
        client_secret="synthetic-secret",
    )

    pack_path.write_text(
        """
pack_id: test-api-user
version: 1.1.0
connector:
  name: Test API User
  base_url: https://api.example.test
oauth:
  authorize_url: https://auth.example.test/authorize
  token_url: https://auth.example.test/token
operations:
  - method: POST
    path: /items.search
    operation_id: test_search_items
    summary: Search synthetic items.
    request_schema: {type: object}
    response_schema: {type: object}
  - method: GET
    path: /items/{id}
    operation_id: test_get_item
    summary: Get one item.
    request_schema: {type: object}
    response_schema: {type: object}
""",
        encoding="utf-8",
    )
    catalog = ApiConnectorPackCatalog(tmp_path)
    service = ApiConnectorService(tenant.id, async_db_session)
    _connector, sync_summary = await _sync_pack(service, catalog, actor=actor, connector_id=created_connector.id)

    assert sync_summary.added == 1
    assert sync_summary.installed_pack_version == "1.1.0"
    operations = await service.operation_repo.list_by_connector(tenant.id, created_connector.id)
    assert {op.operation_id for op in operations} == {"test_search_items", "test_get_item"}


@pytest.mark.asyncio
async def test_sync_stales_removed_pack_operation(async_db_session, tmp_path: Path):
    pack_path = tmp_path / "test-pack.yaml"
    pack_path.write_text(
        """
pack_id: test-api-user
version: 1.0.0
connector:
  name: Test API User
  base_url: https://api.example.test
oauth:
  authorize_url: https://auth.example.test/authorize
  token_url: https://auth.example.test/token
operations:
  - method: POST
    path: /items.search
    operation_id: test_search_items
    summary: Search synthetic items.
    request_schema: {type: object}
    response_schema: {type: object}
  - method: GET
    path: /items/{id}
    operation_id: test_get_item
    summary: Get one item.
    request_schema: {type: object}
    response_schema: {type: object}
""",
        encoding="utf-8",
    )
    tenant, _user, actor = await _seed_tenant_admin(async_db_session, slug="test-pack-stale")
    catalog = ApiConnectorPackCatalog(tmp_path)
    service = ApiConnectorService(tenant.id, async_db_session)
    created_connector, _ = await _install_pack(
        service,
        catalog,
        actor=actor,
        pack_id="test-api-user",
        client_id="synthetic-client",
        client_secret="synthetic-secret",
    )

    pack_path.write_text(
        """
pack_id: test-api-user
version: 1.1.0
connector:
  name: Test API User
  base_url: https://api.example.test
oauth:
  authorize_url: https://auth.example.test/authorize
  token_url: https://auth.example.test/token
operations:
  - method: POST
    path: /items.search
    operation_id: test_search_items
    summary: Search synthetic items.
    request_schema: {type: object}
    response_schema: {type: object}
""",
        encoding="utf-8",
    )
    catalog = ApiConnectorPackCatalog(tmp_path)
    service = ApiConnectorService(tenant.id, async_db_session)
    _connector, sync_summary = await _sync_pack(service, catalog, actor=actor, connector_id=created_connector.id)

    assert sync_summary.staled == 1
    operations = await service.operation_repo.list_by_connector(tenant.id, created_connector.id)
    stale = next(op for op in operations if op.operation_id == "test_get_item")
    assert stale.status == OPERATION_STATUS_STALE


@pytest.mark.asyncio
async def test_sync_expands_oauth_scopes_flags_summary(async_db_session, tmp_path: Path):
    pack_path = tmp_path / "test-pack.yaml"
    pack_path.write_text(
        """
pack_id: test-api-user
version: 1.0.0
connector:
  name: Test API User
  base_url: https://api.example.test
oauth:
  authorize_url: https://auth.example.test/authorize
  token_url: https://auth.example.test/token
  scopes:
    - read:basic
operations:
  - method: POST
    path: /items.search
    operation_id: test_search_items
    summary: Search synthetic items.
    request_schema: {type: object}
    response_schema: {type: object}
""",
        encoding="utf-8",
    )
    tenant, _user, actor = await _seed_tenant_admin(async_db_session, slug="test-pack-scopes")
    catalog = ApiConnectorPackCatalog(tmp_path)
    service = ApiConnectorService(tenant.id, async_db_session)
    created_connector, _ = await _install_pack(
        service,
        catalog,
        actor=actor,
        pack_id="test-api-user",
        client_id="synthetic-client",
        client_secret="synthetic-secret",
    )

    pack_path.write_text(
        """
pack_id: test-api-user
version: 1.0.1
connector:
  name: Test API User
  base_url: https://api.example.test
oauth:
  authorize_url: https://auth.example.test/authorize
  token_url: https://auth.example.test/token
  scopes:
    - read:basic
    - read:extended
operations:
  - method: POST
    path: /items.search
    operation_id: test_search_items
    summary: Search synthetic items.
    request_schema: {type: object}
    response_schema: {type: object}
""",
        encoding="utf-8",
    )
    catalog = ApiConnectorPackCatalog(tmp_path)
    service = ApiConnectorService(tenant.id, async_db_session)
    _connector, sync_summary = await _sync_pack(service, catalog, actor=actor, connector_id=created_connector.id)

    assert sync_summary.scopes_changed is True
    assert sync_summary.scopes_expanded is True


@pytest.mark.asyncio
async def test_sync_rejects_connector_without_pack_ref(async_db_session, tmp_path: Path):
    tenant, user, actor = await _seed_tenant_admin(async_db_session, slug="test-pack-reject")
    connector_svc = ApiConnectorService(tenant_id=tenant.id, db_session=async_db_session)
    created = await connector_svc.create_connector(
        owner_id=user.id,
        name="manual-connector",
        description=None,
        base_url="https://api.example.test",
        auth_type="none",
        auth_config={},
        rate_policy=RatePolicyDomain(),
        schema_source_type="manual",
        schema_source_url=None,
    )
    catalog = ApiConnectorPackCatalog(tmp_path)

    with pytest.raises(ValidationError, match="not backed by an integration pack"):
        await connector_svc.sync_installed_pack_for_connector_for_actor(
            actor=actor,
            connector_id=created.id,
            catalog=catalog,
        )