"""Test helpers for data source and asset fixtures."""

from apps.shared.db.models import AbacPolicy, AssetMetadata, DataSource
from apps.shared.domain.types import ABAC_ACTION_READ, ABAC_ACTION_WRITE, RESOURCE_TYPE_DATA_SOURCE
from tests.helpers.document_fixtures import create_tenant_user

__all__ = [
    "create_tenant_user",
    "create_data_source",
    "create_asset",
    "seed_data_source_owner_policies",
]


async def seed_data_source_owner_policies(session, tenant_id: int, *, base_id: int = 8000) -> None:
    for offset, action in enumerate((ABAC_ACTION_READ, ABAC_ACTION_WRITE)):
        session.add(
            AbacPolicy(
                id=base_id + offset,
                tenant_id=tenant_id,
                name=f"data-source-owner-{action}",
                description=None,
                resource_type=RESOURCE_TYPE_DATA_SOURCE,
                action=action,
                expression=':user.role equals "admin" or :user.id equals :resource.owner_id',
                status="active",
            )
        )
    await session.commit()


async def create_data_source(
    session,
    *,
    tenant_id: int,
    owner_id: int,
    name: str = "test_ds",
    managed: bool = True,
) -> DataSource:
    data_source = DataSource(
        tenant_id=tenant_id,
        name=name,
        type="sqlite",
        managed=managed,
        config={"connection_url": "sqlite:///:memory:"},
        owner_id=owner_id,
    )
    session.add(data_source)
    await session.commit()
    await session.refresh(data_source)
    return data_source


async def create_asset(
    session,
    *,
    data_source_id: int,
    owner_id: int,
    asset_name: str = "orders",
    asset_type: str = "table",
) -> AssetMetadata:
    asset = AssetMetadata(
        data_source_id=data_source_id,
        asset_name=asset_name,
        asset_type=asset_type,
        columns=[],
        source_info={},
        owner_id=owner_id,
    )
    session.add(asset)
    await session.commit()
    await session.refresh(asset)
    return asset
