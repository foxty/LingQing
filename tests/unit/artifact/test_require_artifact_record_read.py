"""Unit tests for require_artifact_record_read."""

from uuid import uuid4

import pytest

from apps.shared.artifact.access import require_artifact_record_read
from apps.shared.core.exceptions import AuthorizationError, ResourceNotFoundError
from apps.shared.core.policy_seed import seed_default_policies
from apps.shared.db.models import ResourceAcl, Tenant, User
from tests.helpers.artifact_access_fixtures import (
    create_standalone_artifact,
    create_tenant_with_users,
    grant_artifact_acl,
)


def _suffix() -> str:
    return uuid4().hex[:8]


@pytest.mark.asyncio
async def test_require_artifact_record_read_owner(async_db_session):
    tenant, owner, _peer = await create_tenant_with_users(
        async_db_session,
        owner_username=f"owner_{_suffix()}",
        peer_username=f"peer_{_suffix()}",
    )
    artifact = await create_standalone_artifact(
        async_db_session,
        tenant_id=tenant.id,
        owner_id=owner.id,
        resource_id=2001,
    )
    record = await require_artifact_record_read(
        db=async_db_session,
        tenant_id=tenant.id,
        user_id=owner.id,
        user_role=owner.role,
        artifact_id=artifact.id,
    )
    assert record.id == artifact.id


@pytest.mark.asyncio
async def test_require_artifact_record_read_peer_with_read_share(async_db_session):
    tenant, owner, peer = await create_tenant_with_users(
        async_db_session,
        owner_username=f"owner_{_suffix()}",
        peer_username=f"peer_{_suffix()}",
    )
    artifact = await create_standalone_artifact(
        async_db_session,
        tenant_id=tenant.id,
        owner_id=owner.id,
        resource_id=2002,
    )
    await grant_artifact_acl(
        async_db_session,
        tenant_id=tenant.id,
        artifact_type="report",
        resource_id=artifact.resource_id,
        owner_id=owner.id,
        grantee_user_id=peer.id,
        permission="read",
    )
    record = await require_artifact_record_read(
        db=async_db_session,
        tenant_id=tenant.id,
        user_id=peer.id,
        user_role=peer.role,
        artifact_id=artifact.id,
    )
    assert record.id == artifact.id


@pytest.mark.asyncio
async def test_require_artifact_record_read_peer_denied_without_share(async_db_session):
    tenant, owner, peer = await create_tenant_with_users(
        async_db_session,
        owner_username=f"owner_{_suffix()}",
        peer_username=f"peer_{_suffix()}",
    )
    artifact = await create_standalone_artifact(
        async_db_session,
        tenant_id=tenant.id,
        owner_id=owner.id,
        resource_id=2003,
    )
    with pytest.raises(AuthorizationError, match="Access denied"):
        await require_artifact_record_read(
            db=async_db_session,
            tenant_id=tenant.id,
            user_id=peer.id,
            user_role=peer.role,
            artifact_id=artifact.id,
        )


@pytest.mark.asyncio
async def test_require_artifact_record_read_not_found(async_db_session):
    tenant, owner, _peer = await create_tenant_with_users(
        async_db_session,
        owner_username=f"owner_{_suffix()}",
        peer_username=f"peer_{_suffix()}",
    )
    with pytest.raises(ResourceNotFoundError, match="Artifact 99999 not found"):
        await require_artifact_record_read(
            db=async_db_session,
            tenant_id=tenant.id,
            user_id=owner.id,
            user_role=owner.role,
            artifact_id=99999,
        )


@pytest.mark.asyncio
async def test_require_artifact_record_read_admin_manage_when_acl_not_configured(async_db_session):
    """Inject path allows artifacts.manage when ResourceAcl row is absent."""
    tenant = Tenant(name=f"tenant_{_suffix()}", slug=f"tenant_{_suffix()}", config=None)
    async_db_session.add(tenant)
    await async_db_session.flush()
    await seed_default_policies(async_db_session, tenant.id)

    owner = User(
        username=f"owner_{_suffix()}",
        email=None,
        hashed_password="hashed",
        role="member",
        tenant_id=tenant.id,
    )
    admin = User(
        username=f"admin_{_suffix()}",
        email=None,
        hashed_password="hashed",
        role="admin",
        tenant_id=tenant.id,
    )
    async_db_session.add_all([owner, admin])
    await async_db_session.commit()
    await async_db_session.refresh(admin)

    artifact = await create_standalone_artifact(
        async_db_session,
        tenant_id=tenant.id,
        owner_id=owner.id,
        resource_id=2004,
    )
    record = await require_artifact_record_read(
        db=async_db_session,
        tenant_id=tenant.id,
        user_id=admin.id,
        user_role=admin.role,
        artifact_id=artifact.id,
    )
    assert record.id == artifact.id


@pytest.mark.asyncio
async def test_require_artifact_record_read_peer_denied_when_acl_active_no_grant(async_db_session):
    tenant, owner, peer = await create_tenant_with_users(
        async_db_session,
        owner_username=f"owner_{_suffix()}",
        peer_username=f"peer_{_suffix()}",
    )
    artifact = await create_standalone_artifact(
        async_db_session,
        tenant_id=tenant.id,
        owner_id=owner.id,
        resource_id=2005,
    )
    async_db_session.add(
        ResourceAcl(
            tenant_id=tenant.id,
            resource_type="report",
            resource_id=artifact.resource_id,
            owner_id=owner.id,
            status="active",
        )
    )
    await async_db_session.commit()
    with pytest.raises(AuthorizationError, match="Access denied"):
        await require_artifact_record_read(
            db=async_db_session,
            tenant_id=tenant.id,
            user_id=peer.id,
            user_role=peer.role,
            artifact_id=artifact.id,
        )
