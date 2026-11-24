"""Delete API connector cleans polymorphic dependents (credentials, ACL, tags)."""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import select

from apps.shared.db.models import AclGrant, ResourceAcl, Tenant, User
from apps.shared.domain.actor import ActorContext
from apps.shared.domain.types import RESOURCE_TYPE_API_CONNECTOR
from apps.shared.external_systems.api_connector.domain import RatePolicyDomain
from apps.shared.external_systems.api_connector.service import ApiConnectorService
from apps.shared.external_systems.credentials.repository import UserIntegrationCredentialRepository
from apps.shared.utils.field_cipher import FieldCipher


@pytest.mark.asyncio
async def test_delete_connector_removes_user_credentials_and_acl(async_db_session):
    suffix = uuid4().hex[:8]
    tenant = Tenant(name=f"del_conn_{suffix}", slug=f"del-conn-{suffix}", config=None)
    async_db_session.add(tenant)
    await async_db_session.flush()

    owner = User(
        username=f"del_owner_{suffix}",
        email=None,
        hashed_password="synthetic",
        role="admin",
        tenant_id=tenant.id,
    )
    peer = User(
        username=f"del_peer_{suffix}",
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

    await service.delete_connector_for_actor(connector_id=connector.id, actor=actor)

    remaining_bindings = await cred_repo.list_bindings_for_resource(
        tenant_id=tenant.id,
        resource_type=RESOURCE_TYPE_API_CONNECTOR,
        resource_id=connector.id,
    )
    assert remaining_bindings == []

    grants = await async_db_session.execute(
        select(AclGrant).where(
            AclGrant.tenant_id == tenant.id,
            AclGrant.resource_type == RESOURCE_TYPE_API_CONNECTOR,
            AclGrant.resource_id == connector.id,
        )
    )
    assert grants.scalars().all() == []

    acls = await async_db_session.execute(
        select(ResourceAcl).where(
            ResourceAcl.tenant_id == tenant.id,
            ResourceAcl.resource_type == RESOURCE_TYPE_API_CONNECTOR,
            ResourceAcl.resource_id == connector.id,
        )
    )
    assert acls.scalars().all() == []

    assert await service.connector_repo.get_by_id_and_tenant(connector.id, tenant.id) is None
