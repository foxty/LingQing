"""Integration: pack install + connector delete cascade (real Postgres)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy import select

from apps.shared.db.models import (
    AclGrant,
    ApiOperationIndex,
    ResourceAcl,
    ResourceIndex,
    Tenant,
    User,
)
from apps.shared.domain.actor import ActorContext
from apps.shared.domain.types import RESOURCE_TYPE_API_CONNECTOR
from apps.shared.external_systems.api_connector.domain import RatePolicyDomain
from apps.shared.external_systems.api_connector.service import ApiConnectorService
from apps.shared.external_systems.credentials.repository import UserIntegrationCredentialRepository
from apps.shared.external_systems.packs.loader import ApiConnectorPackCatalog
from apps.shared.external_systems.packs.schemas import InstallApiConnectorPackRequest
from apps.shared.external_systems.packs.service import ApiConnectorPackService
from apps.shared.search.sync_service import ResourceIndexService
from apps.shared.utils.field_cipher import FieldCipher


@pytest.fixture
def stub_resource_index_service(monkeypatch):
    """Avoid Chroma/embedding setup while still deleting ResourceIndex rows."""

    @classmethod
    async def _create(cls, tenant_id, db_session, **_kwargs):
        service = cls(tenant_id=tenant_id, db_session=db_session, embeddings=MagicMock())
        service.rag_manager.remove_by_resource = AsyncMock(return_value=0)
        service.rag_manager.remove_by_resources = AsyncMock(return_value=0)
        return service

    monkeypatch.setattr(ResourceIndexService, "create", _create)


@pytest.mark.asyncio
async def test_builtin_slack_pack_install_persists_connector_and_operations(async_db_session):
    suffix = uuid4().hex[:8]
    tenant = Tenant(name=f"pack_inst_{suffix}", slug=f"pack-inst-{suffix}", config=None)
    async_db_session.add(tenant)
    await async_db_session.flush()
    user = User(
        username=f"pack_admin_{suffix}",
        email=None,
        hashed_password="synthetic",
        role="admin",
        tenant_id=tenant.id,
    )
    async_db_session.add(user)
    await async_db_session.flush()
    actor = ActorContext(tenant_id=tenant.id, user_id=user.id, user_role=user.role)

    catalog = ApiConnectorPackCatalog()
    manifest = catalog.get("slack-user")
    service = ApiConnectorPackService(tenant.id, async_db_session, catalog=catalog)
    request = InstallApiConnectorPackRequest(
        pack_id="slack-user",
        client_id="synthetic-client",
        client_secret="synthetic-secret",
        redirect_uri="https://api.example.test/integrations/oauth/callback",
    )

    created = await service.install(actor=actor, request=request)
    repeated = await service.install(actor=actor, request=request)

    assert created.id == repeated.id
    assert created.pack_ref == manifest.pack_ref
    assert created.auth_type == "oauth2"
    assert created.credential_mode == "user"
    assert created.base_url == "https://slack.com/api"
    assert created.execution_rules.default_request_encoding == "form"
    assert created.execution_rules.success_json_path == "ok"

    connector_svc = ApiConnectorService(tenant_id=tenant.id, db_session=async_db_session)
    operations = await connector_svc.operation_repo.list_by_connector(tenant.id, created.id)
    assert {op.operation_id for op in operations} == {
        operation.operation_id for operation in manifest.operations
    }
    assert all(op.connector_id == created.id for op in operations)
    assert all(op.tenant_id == tenant.id for op in operations)


@pytest.mark.asyncio
async def test_delete_connector_removes_credentials_acl_ops_and_resource_index(
    async_db_session,
    stub_resource_index_service,
):
    suffix = uuid4().hex[:8]
    tenant = Tenant(name=f"pack_del_{suffix}", slug=f"pack-del-{suffix}", config=None)
    async_db_session.add(tenant)
    await async_db_session.flush()

    owner = User(
        username=f"pack_del_owner_{suffix}",
        email=None,
        hashed_password="synthetic",
        role="admin",
        tenant_id=tenant.id,
    )
    peer = User(
        username=f"pack_del_peer_{suffix}",
        email=None,
        hashed_password="synthetic",
        role="member",
        tenant_id=tenant.id,
    )
    async_db_session.add_all([owner, peer])
    await async_db_session.flush()

    actor = ActorContext(tenant_id=tenant.id, user_id=owner.id, user_role=owner.role)
    service = ApiConnectorService(tenant_id=tenant.id, db_session=async_db_session)
    connector = await service.create_connector(
        owner_id=owner.id,
        name=f"del-oauth-{suffix}",
        description=None,
        base_url="https://slack.com/api",
        auth_type="oauth2",
        auth_config={
            "auth_method": "oauth2",
            "authorize_url": "https://slack.com/oauth/v2/authorize",
            "token_url": "https://slack.com/api/oauth.v2.access",
            "client_id": "synthetic-client",
            "client_secret": "synthetic-secret",
            "scopes": ["search:read"],
        },
        rate_policy=RatePolicyDomain(),
        schema_source_type="manual",
        schema_source_url=None,
        credential_mode="user",
    )
    operation = await service.add_manual_operation_for_actor(
        connector_id=connector.id,
        actor=actor,
        method="POST",
        path_template="/search.messages",
        operation_id=f"slack_search_{suffix}",
        summary="Search",
        description=None,
        tags=["slack"],
        request_schema={"type": "object"},
        response_schema={"type": "object"},
    )

    cipher = FieldCipher()
    cred_repo = UserIntegrationCredentialRepository(async_db_session)
    await cred_repo.upsert_binding(
        tenant_id=tenant.id,
        user_id=owner.id,
        resource_type=RESOURCE_TYPE_API_CONNECTOR,
        resource_id=connector.id,
        auth_type="oauth2",
        secrets_enc=cipher.encrypt_dict(
            {"access_token": "xoxp-owner"},
            sensitive_fields={"access_token"},
        ),
        account_label="owner",
    )
    await cred_repo.upsert_binding(
        tenant_id=tenant.id,
        user_id=peer.id,
        resource_type=RESOURCE_TYPE_API_CONNECTOR,
        resource_id=connector.id,
        auth_type="oauth2",
        secrets_enc=cipher.encrypt_dict(
            {"access_token": "xoxp-peer"},
            sensitive_fields={"access_token"},
        ),
        account_label="peer",
    )

    async_db_session.add(
        ResourceAcl(
            tenant_id=tenant.id,
            resource_type=RESOURCE_TYPE_API_CONNECTOR,
            resource_id=connector.id,
            owner_id=owner.id,
            status="active",
        )
    )
    async_db_session.add(
        AclGrant(
            tenant_id=tenant.id,
            resource_type=RESOURCE_TYPE_API_CONNECTOR,
            resource_id=connector.id,
            principal_type="user",
            principal_id=str(peer.id),
            permission="read",
            effect="allow",
            created_by=owner.id,
        )
    )
    await async_db_session.flush()

    # add_manual_operation registers a ResourceIndex row for the operation
    indexed = await async_db_session.execute(
        select(ResourceIndex).where(
            ResourceIndex.tenant_id == tenant.id,
            ResourceIndex.resource_type == RESOURCE_TYPE_API_CONNECTOR,
            ResourceIndex.resource_id == operation.id,
        )
    )
    assert indexed.scalar_one_or_none() is not None

    operation_id = operation.id
    connector_id = connector.id

    await service.delete_connector_for_actor(connector_id=connector_id, actor=actor)

    assert await cred_repo.list_bindings_for_resource(
        tenant_id=tenant.id,
        resource_type=RESOURCE_TYPE_API_CONNECTOR,
        resource_id=connector_id,
    ) == []

    grants = await async_db_session.execute(
        select(AclGrant).where(
            AclGrant.tenant_id == tenant.id,
            AclGrant.resource_type == RESOURCE_TYPE_API_CONNECTOR,
            AclGrant.resource_id == connector_id,
        )
    )
    assert grants.scalars().all() == []

    acls = await async_db_session.execute(
        select(ResourceAcl).where(
            ResourceAcl.tenant_id == tenant.id,
            ResourceAcl.resource_type == RESOURCE_TYPE_API_CONNECTOR,
            ResourceAcl.resource_id == connector_id,
        )
    )
    assert acls.scalars().all() == []

    ops = await async_db_session.execute(
        select(ApiOperationIndex).where(
            ApiOperationIndex.tenant_id == tenant.id,
            ApiOperationIndex.connector_id == connector_id,
        )
    )
    assert ops.scalars().all() == []

    indexes = await async_db_session.execute(
        select(ResourceIndex).where(
            ResourceIndex.tenant_id == tenant.id,
            ResourceIndex.resource_type == RESOURCE_TYPE_API_CONNECTOR,
            ResourceIndex.resource_id == operation_id,
        )
    )
    assert indexes.scalars().all() == []

    assert await service.connector_repo.get_by_id_and_tenant(connector_id, tenant.id) is None
