"""Unit tests for asset metadata container authz via data source."""

import pytest

from apps.shared.core.exceptions import AuthorizationError
from apps.shared.data_source.asset_metadata_service import AssetMetadataService
from apps.shared.data_source.repository import AssetMetadataRepository
from apps.shared.db.models import User
from apps.shared.domain.actor import ActorContext
from tests.helpers.data_source_fixtures import (
    create_asset,
    create_data_source,
    create_tenant_user,
    seed_data_source_owner_policies,
)


@pytest.mark.asyncio
async def test_list_assets_for_actor_inherits_data_source_read(async_db_session):
    tenant, owner = await create_tenant_user(async_db_session, tenant_name="ds-list-t1", username="ds-owner")
    await seed_data_source_owner_policies(async_db_session, tenant.id)

    other = User(username="asset-uploader", email=None, hashed_password="hashed", role="member", tenant_id=tenant.id)
    async_db_session.add(other)
    await async_db_session.commit()
    await async_db_session.refresh(other)

    data_source = await create_data_source(async_db_session, tenant_id=tenant.id, owner_id=owner.id, name="Warehouse")
    await create_asset(
        async_db_session,
        data_source_id=data_source.id,
        owner_id=other.id,
        asset_name="orders",
    )

    service = AssetMetadataService(tenant_id=tenant.id, db_session=async_db_session)
    assets, pagination = await service.list_assets_for_actor(
        actor=ActorContext(tenant_id=tenant.id, user_id=owner.id, user_role="member"),
        data_source_id=data_source.id,
    )

    assert pagination.total == 1
    assert len(assets) == 1
    assert assets[0].asset_name == "orders"


@pytest.mark.asyncio
async def test_list_assets_for_actor_denied_without_data_source_access(async_db_session):
    tenant, owner = await create_tenant_user(async_db_session, tenant_name="ds-list-t2", username="ds-owner2")
    await seed_data_source_owner_policies(async_db_session, tenant.id, base_id=8100)

    other = User(username="ds-stranger", email=None, hashed_password="hashed", role="member", tenant_id=tenant.id)
    async_db_session.add(other)
    await async_db_session.commit()
    await async_db_session.refresh(other)

    data_source = await create_data_source(async_db_session, tenant_id=tenant.id, owner_id=owner.id, name="Private")
    await create_asset(async_db_session, data_source_id=data_source.id, owner_id=owner.id, asset_name="secret")

    service = AssetMetadataService(tenant_id=tenant.id, db_session=async_db_session)
    with pytest.raises(AuthorizationError):
        await service.list_assets_for_actor(
            actor=ActorContext(tenant_id=tenant.id, user_id=other.id, user_role="member"),
            data_source_id=data_source.id,
        )


@pytest.mark.asyncio
async def test_get_asset_by_id_denied_when_data_source_inaccessible_even_if_asset_owner(async_db_session):
    tenant, owner = await create_tenant_user(async_db_session, tenant_name="ds-get-t1", username="ds-owner3")
    await seed_data_source_owner_policies(async_db_session, tenant.id, base_id=8200)

    other = User(username="asset-owner-not-ds-owner", email=None, hashed_password="hashed", role="member", tenant_id=tenant.id)
    async_db_session.add(other)
    await async_db_session.commit()
    await async_db_session.refresh(other)

    data_source = await create_data_source(async_db_session, tenant_id=tenant.id, owner_id=owner.id, name="Locked")
    asset = await create_asset(
        async_db_session,
        data_source_id=data_source.id,
        owner_id=other.id,
        asset_name="my_table",
    )

    service = AssetMetadataService(tenant_id=tenant.id, db_session=async_db_session)
    with pytest.raises(AuthorizationError):
        await service.get_asset_by_id_for_actor(
            actor=ActorContext(tenant_id=tenant.id, user_id=other.id, user_role="member"),
            asset_id=asset.id,
        )


@pytest.mark.asyncio
async def test_delete_assets_for_actor_inherits_data_source_write(async_db_session):
    tenant, owner = await create_tenant_user(async_db_session, tenant_name="ds-del-t1", username="ds-owner4")
    await seed_data_source_owner_policies(async_db_session, tenant.id, base_id=8300)

    other = User(username="other-uploader", email=None, hashed_password="hashed", role="member", tenant_id=tenant.id)
    async_db_session.add(other)
    await async_db_session.commit()
    await async_db_session.refresh(other)

    data_source = await create_data_source(async_db_session, tenant_id=tenant.id, owner_id=owner.id, name="Shared")
    await create_asset(
        async_db_session,
        data_source_id=data_source.id,
        owner_id=other.id,
        asset_name="legacy_orders",
    )

    service = AssetMetadataService(tenant_id=tenant.id, db_session=async_db_session)
    deleted_count, failed, errors = await service.delete_assets_for_actor(
        actor=ActorContext(tenant_id=tenant.id, user_id=owner.id, user_role="member"),
        data_source_id=data_source.id,
        asset_names=["legacy_orders"],
    )

    assert deleted_count == 1
    assert failed == []
    assert errors == {}

    repo = AssetMetadataRepository(async_db_session)
    assert await repo.get_by_data_source_and_name(data_source.id, "legacy_orders") is None


@pytest.mark.asyncio
async def test_delete_assets_for_actor_denied_without_data_source_write(async_db_session):
    tenant, owner = await create_tenant_user(async_db_session, tenant_name="ds-del-t2", username="ds-owner5")
    await seed_data_source_owner_policies(async_db_session, tenant.id, base_id=8400)

    other = User(username="cannot-delete", email=None, hashed_password="hashed", role="member", tenant_id=tenant.id)
    async_db_session.add(other)
    await async_db_session.commit()
    await async_db_session.refresh(other)

    data_source = await create_data_source(async_db_session, tenant_id=tenant.id, owner_id=owner.id, name="Protected")
    await create_asset(
        async_db_session,
        data_source_id=data_source.id,
        owner_id=other.id,
        asset_name="owned_but_locked",
    )

    service = AssetMetadataService(tenant_id=tenant.id, db_session=async_db_session)
    with pytest.raises(AuthorizationError):
        await service.delete_assets_for_actor(
            actor=ActorContext(tenant_id=tenant.id, user_id=other.id, user_role="member"),
            data_source_id=data_source.id,
            asset_names=["owned_but_locked"],
        )
