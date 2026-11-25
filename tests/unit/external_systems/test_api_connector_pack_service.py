from pathlib import Path

import pytest

from apps.shared.db.models import ApiConnector, Tenant, User
from apps.shared.domain.actor import ActorContext
from apps.shared.external_systems.packs.loader import ApiConnectorPackCatalog
from apps.shared.external_systems.packs.schemas import InstallApiConnectorPackRequest
from apps.shared.external_systems.packs.service import ApiConnectorPackService


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
    tenant = Tenant(name="test_pack_tenant", slug="test-pack-tenant", config=None)
    async_db_session.add(tenant)
    await async_db_session.flush()
    user = User(
        username="test_pack_admin",
        email=None,
        hashed_password="synthetic",
        role="admin",
        tenant_id=tenant.id,
    )
    async_db_session.add(user)
    await async_db_session.flush()
    actor = ActorContext(tenant_id=tenant.id, user_id=user.id, user_role=user.role)
    service = ApiConnectorPackService(
        tenant.id,
        async_db_session,
        catalog=ApiConnectorPackCatalog(tmp_path),
    )
    request = InstallApiConnectorPackRequest(
        pack_id="test-api-user",
        client_id="synthetic-client",
        client_secret="synthetic-secret",
    )

    created = await service.install(actor=actor, request=request)
    connector = await async_db_session.get(ApiConnector, created.id)
    assert connector is not None
    connector.agent_instructions = "stale instructions"
    await async_db_session.flush()
    repeated = await service.install(actor=actor, request=request)

    assert created.id == repeated.id
    assert created.pack_ref == "test-api-user@1"
    assert repeated.agent_instructions == "Use focused searches and keep calls read-only."
    assert created.execution_rules.default_request_encoding == "json"
