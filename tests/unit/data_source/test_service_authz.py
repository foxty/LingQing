"""Unit tests for data-source container asset authorization."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from apps.shared.core.exceptions import AuthorizationError, ResourceNotFoundError
from apps.shared.data_source.repository import AssetMetadataRepository, DataSourceRepository
from apps.shared.data_source.service import DataSourceService
from apps.shared.db.models import AclGrant, AssetMetadata, ResourceAcl, ResourceIndex, User
from apps.shared.domain.actor import ActorContext
from apps.shared.domain.types import ABAC_ACTION_READ, RESOURCE_TYPE_ASSET
from tests.helpers.data_source_fixtures import (
    create_asset,
    create_data_source,
    create_tenant_user,
    seed_data_source_owner_policies,
)


async def _build_service(session, tenant_id: int) -> DataSourceService:
    return DataSourceService(
        tenant_id=tenant_id,
        data_source_repo=DataSourceRepository(session),
        asset_repo=AssetMetadataRepository(session),
    )


@pytest.mark.asyncio
async def test_build_asset_access_scope_owner_can_read_own_data_source_assets(async_db_session):
    tenant, owner = await create_tenant_user(async_db_session, tenant_name="ds-scope-t1", username="scope-owner")
    await seed_data_source_owner_policies(async_db_session, tenant.id)

    data_source = await create_data_source(async_db_session, tenant_id=tenant.id, owner_id=owner.id, name="Mine")
    asset = await create_asset(async_db_session, data_source_id=data_source.id, owner_id=owner.id, asset_name="orders")

    service = await _build_service(async_db_session, tenant.id)
    actor = ActorContext(tenant_id=tenant.id, user_id=owner.id, user_role="member")
    scope = await service.build_asset_access_scope(actor=actor, action=ABAC_ACTION_READ)

    assert scope.deny_all is False
    assert scope.allow_all is False
    assert scope.asset_filter is not None

    stmt = select(AssetMetadata.id).where(scope.asset_filter)
    visible_ids = set((await async_db_session.execute(stmt)).scalars().all())
    assert visible_ids == {asset.id}


@pytest.mark.asyncio
async def test_build_asset_access_scope_other_user_denied_by_default(async_db_session):
    tenant, owner = await create_tenant_user(async_db_session, tenant_name="ds-scope-t2", username="scope-owner2")
    await seed_data_source_owner_policies(async_db_session, tenant.id, base_id=8500)

    other = User(username="scope-other", email=None, hashed_password="hashed", role="member", tenant_id=tenant.id)
    async_db_session.add(other)
    await async_db_session.commit()
    await async_db_session.refresh(other)

    data_source = await create_data_source(async_db_session, tenant_id=tenant.id, owner_id=owner.id, name="Private")
    await create_asset(async_db_session, data_source_id=data_source.id, owner_id=owner.id, asset_name="hidden")

    service = await _build_service(async_db_session, tenant.id)
    actor = ActorContext(tenant_id=tenant.id, user_id=other.id, user_role="member")
    scope = await service.build_asset_access_scope(actor=actor, action=ABAC_ACTION_READ)

    stmt = select(AssetMetadata.id).where(scope.asset_filter)
    visible_ids = set((await async_db_session.execute(stmt)).scalars().all())
    assert visible_ids == set()


@pytest.mark.asyncio
async def test_build_asset_access_scope_index_parent_filter(async_db_session):
    tenant, owner = await create_tenant_user(async_db_session, tenant_name="ds-scope-t3", username="scope-owner3")
    await seed_data_source_owner_policies(async_db_session, tenant.id, base_id=8600)

    other = User(username="scope-other2", email=None, hashed_password="hashed", role="member", tenant_id=tenant.id)
    async_db_session.add(other)
    await async_db_session.commit()
    await async_db_session.refresh(other)

    allowed_ds = await create_data_source(async_db_session, tenant_id=tenant.id, owner_id=owner.id, name="Allowed")
    denied_ds = await create_data_source(async_db_session, tenant_id=tenant.id, owner_id=other.id, name="Denied")
    allowed_asset = await create_asset(
        async_db_session,
        data_source_id=allowed_ds.id,
        owner_id=owner.id,
        asset_name="allowed_orders",
    )
    denied_asset = await create_asset(
        async_db_session,
        data_source_id=denied_ds.id,
        owner_id=other.id,
        asset_name="denied_orders",
    )

    for asset, data_source in (
        (allowed_asset, allowed_ds),
        (denied_asset, denied_ds),
    ):
        async_db_session.add(
            ResourceIndex(
                tenant_id=tenant.id,
                resource_type=RESOURCE_TYPE_ASSET,
                resource_id=asset.id,
                owner_id=asset.owner_id,
                parent_id=data_source.id,
                tokenized_content=asset.asset_name,
            )
        )
    await async_db_session.commit()

    service = await _build_service(async_db_session, tenant.id)
    actor = ActorContext(tenant_id=tenant.id, user_id=owner.id, user_role="member")
    scope = await service.build_asset_access_scope(actor=actor, action=ABAC_ACTION_READ)

    assert scope.index_parent_filter is not None
    stmt = (
        select(ResourceIndex.resource_id)
        .where(
            ResourceIndex.tenant_id == tenant.id,
            ResourceIndex.resource_type == RESOURCE_TYPE_ASSET,
            scope.index_parent_filter,
        )
    )
    visible_ids = set((await async_db_session.execute(stmt)).scalars().all())
    assert visible_ids == {allowed_asset.id}


@pytest.mark.asyncio
async def test_build_asset_access_scope_acl_share_grants_read(async_db_session):
    tenant, owner = await create_tenant_user(async_db_session, tenant_name="ds-scope-t4", username="scope-owner4")
    await seed_data_source_owner_policies(async_db_session, tenant.id, base_id=8700)

    viewer = User(username="scope-viewer", email=None, hashed_password="hashed", role="member", tenant_id=tenant.id)
    async_db_session.add(viewer)
    await async_db_session.commit()
    await async_db_session.refresh(viewer)

    data_source = await create_data_source(async_db_session, tenant_id=tenant.id, owner_id=owner.id, name="Shared")
    asset = await create_asset(async_db_session, data_source_id=data_source.id, owner_id=owner.id, asset_name="shared")

    async_db_session.add(
        ResourceAcl(
            tenant_id=tenant.id,
            resource_type="data_source",
            resource_id=data_source.id,
            owner_id=owner.id,
            status="active",
        )
    )
    async_db_session.add(
        AclGrant(
            tenant_id=tenant.id,
            resource_type="data_source",
            resource_id=data_source.id,
            principal_type="user",
            principal_id=str(viewer.id),
            permission="read",
            effect="allow",
            created_by=owner.id,
        )
    )
    await async_db_session.commit()

    service = await _build_service(async_db_session, tenant.id)
    actor = ActorContext(tenant_id=tenant.id, user_id=viewer.id, user_role="member")
    scope = await service.build_asset_access_scope(actor=actor, action=ABAC_ACTION_READ)

    stmt = select(AssetMetadata.id).where(scope.asset_filter)
    visible_ids = set((await async_db_session.execute(stmt)).scalars().all())
    assert visible_ids == {asset.id}


@pytest.mark.asyncio
async def test_require_asset_access_denied_when_data_source_inaccessible(async_db_session):
    tenant, owner = await create_tenant_user(async_db_session, tenant_name="ds-req-t1", username="req-owner")
    await seed_data_source_owner_policies(async_db_session, tenant.id, base_id=8800)

    other = User(username="req-other", email=None, hashed_password="hashed", role="member", tenant_id=tenant.id)
    async_db_session.add(other)
    await async_db_session.commit()
    await async_db_session.refresh(other)

    data_source = await create_data_source(async_db_session, tenant_id=tenant.id, owner_id=owner.id, name="Locked")
    asset = await create_asset(async_db_session, data_source_id=data_source.id, owner_id=other.id, asset_name="mine")

    service = await _build_service(async_db_session, tenant.id)
    with pytest.raises(AuthorizationError):
        await service.require_asset_access(
            asset_id=asset.id,
            actor=ActorContext(tenant_id=tenant.id, user_id=other.id, user_role="member"),
            action=ABAC_ACTION_READ,
        )


@pytest.mark.asyncio
async def test_require_asset_access_inherits_data_source_read(monkeypatch):
    service = DataSourceService.__new__(DataSourceService)
    service.tenant_id = 1
    service.data_source_repo = SimpleNamespace(db=AsyncMock())

    async def _scalar(_stmt):
        return 42

    service.data_source_repo.db.scalar = AsyncMock(side_effect=_scalar)
    service.require_data_source_access_for_actor = AsyncMock(return_value=(object(), False))

    actor = ActorContext(tenant_id=1, user_id=2, user_role="member")
    data_source_id = await service.require_asset_access(asset_id=99, actor=actor, action="read")

    assert data_source_id == 42
    service.require_data_source_access_for_actor.assert_awaited_once()


@pytest.mark.asyncio
async def test_require_asset_access_not_found():
    service = DataSourceService.__new__(DataSourceService)
    service.tenant_id = 1
    service.data_source_repo = SimpleNamespace(db=AsyncMock())
    service.data_source_repo.db.scalar = AsyncMock(return_value=None)

    actor = ActorContext(tenant_id=1, user_id=2, user_role="member")
    with pytest.raises(ResourceNotFoundError, match="Asset 99 not found"):
        await service.require_asset_access(asset_id=99, actor=actor, action="read")


@pytest.mark.asyncio
async def test_build_asset_access_scope_deny_all(monkeypatch):
    from apps.shared.authz.authz_query_builder import AuthzSqlFilter

    service = DataSourceService.__new__(DataSourceService)
    service.tenant_id = 1
    service._build_data_source_auth_scope = AsyncMock(
        return_value=AuthzSqlFilter(allow_all=False, deny_all=True, clause=None)
    )

    actor = ActorContext(tenant_id=1, user_id=2, user_role="member")
    scope = await service.build_asset_access_scope(actor=actor, action="read")

    assert scope.deny_all is True
    assert scope.allow_all is False
    assert scope.asset_filter is None
    assert scope.index_parent_filter is None


@pytest.mark.asyncio
async def test_build_asset_access_scope_allow_all(monkeypatch):
    from apps.shared.authz.authz_query_builder import AuthzSqlFilter

    service = DataSourceService.__new__(DataSourceService)
    service.tenant_id = 1
    service._build_data_source_auth_scope = AsyncMock(
        return_value=AuthzSqlFilter(allow_all=True, deny_all=False, clause=None)
    )

    actor = ActorContext(tenant_id=1, user_id=2, user_role="member")
    scope = await service.build_asset_access_scope(actor=actor, action="read")

    assert scope.deny_all is False
    assert scope.allow_all is True
    assert scope.asset_filter is None
    assert scope.index_parent_filter is None


@pytest.mark.asyncio
async def test_build_asset_access_scope_scoped_filters():
    from sqlalchemy import true

    from apps.shared.authz.authz_query_builder import AuthzSqlFilter

    service = DataSourceService.__new__(DataSourceService)
    service.tenant_id = 1
    service._build_data_source_auth_scope = AsyncMock(
        return_value=AuthzSqlFilter(allow_all=False, deny_all=False, clause=true())
    )

    actor = ActorContext(tenant_id=1, user_id=2, user_role="member")
    scope = await service.build_asset_access_scope(actor=actor, action="read")

    assert scope.deny_all is False
    assert scope.allow_all is False
    assert scope.asset_filter is not None
    assert scope.index_parent_filter is not None
