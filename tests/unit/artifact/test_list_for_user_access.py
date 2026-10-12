"""Unit tests for ArtifactRepository.list_for_user_access (owner + ACL SQL)."""

from uuid import uuid4

import pytest

from apps.shared.artifact.repository import ArtifactRepository
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
async def test_list_for_user_access_includes_owned_artifacts(async_db_session):
    tenant, owner, _peer = await create_tenant_with_users(
        async_db_session,
        owner_username=f"owner_{_suffix()}",
        peer_username=f"peer_{_suffix()}",
    )
    owned = await create_standalone_artifact(
        async_db_session,
        tenant_id=tenant.id,
        owner_id=owner.id,
        resource_id=1001,
        title="Owner Report Alpha",
    )
    repo = ArtifactRepository(async_db_session)
    rows = await repo.list_for_user_access(tenant_id=tenant.id, user_id=owner.id)
    assert {a.id for a in rows} == {owned.id}


@pytest.mark.asyncio
async def test_list_for_user_access_excludes_other_users_without_grant(async_db_session):
    tenant, owner, peer = await create_tenant_with_users(
        async_db_session,
        owner_username=f"owner_{_suffix()}",
        peer_username=f"peer_{_suffix()}",
    )
    await create_standalone_artifact(
        async_db_session,
        tenant_id=tenant.id,
        owner_id=owner.id,
        resource_id=1002,
        title="Private Report",
    )
    repo = ArtifactRepository(async_db_session)
    peer_rows = await repo.list_for_user_access(tenant_id=tenant.id, user_id=peer.id)
    assert peer_rows == []


@pytest.mark.asyncio
async def test_list_for_user_access_includes_peer_with_read_share(async_db_session):
    tenant, owner, peer = await create_tenant_with_users(
        async_db_session,
        owner_username=f"owner_{_suffix()}",
        peer_username=f"peer_{_suffix()}",
    )
    shared = await create_standalone_artifact(
        async_db_session,
        tenant_id=tenant.id,
        owner_id=owner.id,
        resource_id=1003,
        title="Shared Read Report",
    )
    await grant_artifact_acl(
        async_db_session,
        tenant_id=tenant.id,
        artifact_type="report",
        resource_id=shared.resource_id,
        owner_id=owner.id,
        grantee_user_id=peer.id,
        permission="read",
    )
    repo = ArtifactRepository(async_db_session)
    peer_rows = await repo.list_for_user_access(tenant_id=tenant.id, user_id=peer.id)
    assert {a.id for a in peer_rows} == {shared.id}


@pytest.mark.asyncio
async def test_list_for_user_access_includes_peer_with_write_share_only(async_db_session):
    tenant, owner, peer = await create_tenant_with_users(
        async_db_session,
        owner_username=f"owner_{_suffix()}",
        peer_username=f"peer_{_suffix()}",
    )
    shared = await create_standalone_artifact(
        async_db_session,
        tenant_id=tenant.id,
        owner_id=owner.id,
        resource_id=1004,
        title="Shared Write Report",
    )
    await grant_artifact_acl(
        async_db_session,
        tenant_id=tenant.id,
        artifact_type="report",
        resource_id=shared.resource_id,
        owner_id=owner.id,
        grantee_user_id=peer.id,
        permission="write",
    )
    repo = ArtifactRepository(async_db_session)
    peer_rows = await repo.list_for_user_access(tenant_id=tenant.id, user_id=peer.id)
    assert {a.id for a in peer_rows} == {shared.id}


@pytest.mark.asyncio
async def test_list_for_user_access_excludes_peer_when_resource_acl_has_no_allow_grant(async_db_session):
    tenant, owner, peer = await create_tenant_with_users(
        async_db_session,
        owner_username=f"owner_{_suffix()}",
        peer_username=f"peer_{_suffix()}",
    )
    locked = await create_standalone_artifact(
        async_db_session,
        tenant_id=tenant.id,
        owner_id=owner.id,
        resource_id=1005,
        title="ACL Locked Report",
    )
    async_db_session.add(
        ResourceAcl(
            tenant_id=tenant.id,
            resource_type="report",
            resource_id=locked.resource_id,
            owner_id=owner.id,
            status="active",
        )
    )
    await async_db_session.commit()
    repo = ArtifactRepository(async_db_session)
    peer_rows = await repo.list_for_user_access(tenant_id=tenant.id, user_id=peer.id)
    assert peer_rows == []


@pytest.mark.asyncio
async def test_list_for_user_access_title_query_filter(async_db_session):
    tenant, owner, _peer = await create_tenant_with_users(
        async_db_session,
        owner_username=f"owner_{_suffix()}",
        peer_username=f"peer_{_suffix()}",
    )
    alpha = await create_standalone_artifact(
        async_db_session,
        tenant_id=tenant.id,
        owner_id=owner.id,
        resource_id=1006,
        title="Alpha Dashboard",
        artifact_type="dashboard",
    )
    await create_standalone_artifact(
        async_db_session,
        tenant_id=tenant.id,
        owner_id=owner.id,
        resource_id=1007,
        title="Beta Dashboard",
        artifact_type="dashboard",
    )
    repo = ArtifactRepository(async_db_session)
    rows = await repo.list_for_user_access(
        tenant_id=tenant.id,
        user_id=owner.id,
        query="alpha",
    )
    assert {a.id for a in rows} == {alpha.id}


@pytest.mark.asyncio
async def test_list_for_user_access_admin_without_acl_does_not_see_others(async_db_session):
    """artifacts.manage does not widen context-picker listing."""
    tenant = Tenant(name=f"tenant_admin_{_suffix()}", slug=f"tenant_admin_{_suffix()}", config=None)
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

    await create_standalone_artifact(
        async_db_session,
        tenant_id=tenant.id,
        owner_id=owner.id,
        resource_id=1008,
        title="Owner Only",
    )
    repo = ArtifactRepository(async_db_session)
    admin_rows = await repo.list_for_user_access(tenant_id=tenant.id, user_id=admin.id)
    assert admin_rows == []
