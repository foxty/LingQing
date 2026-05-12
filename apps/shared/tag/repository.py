"""Repositories for tag system and ABAC policies."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.db.base_repository import BaseRepository
from apps.shared.db.models import ResourceTagConfig, TagBinding, TagKey, TagValue


class TagKeyRepository(BaseRepository[TagKey]):
    """Repository for tag keys."""

    def __init__(self, db: AsyncSession):
        super().__init__(TagKey, db)

    async def list_by_tenant(self, tenant_id: int) -> list[TagKey]:
        result = await self.db.execute(select(TagKey).where(TagKey.tenant_id == tenant_id))
        return list(result.scalars().all())

    async def get_by_name(self, tenant_id: int, name: str) -> TagKey | None:
        result = await self.db.execute(select(TagKey).where(TagKey.tenant_id == tenant_id, TagKey.name == name))
        return result.scalar_one_or_none()

    async def get_by_id_and_tenant(self, tenant_id: int, tag_key_id: int) -> TagKey | None:
        result = await self.db.execute(select(TagKey).where(TagKey.tenant_id == tenant_id, TagKey.id == tag_key_id))
        return result.scalar_one_or_none()

    async def has_any_for_tenant(self, tenant_id: int) -> bool:
        result = await self.db.execute(select(TagKey.id).where(TagKey.tenant_id == tenant_id).limit(1))
        return result.scalar_one_or_none() is not None

    async def create_many(self, entities: list[TagKey]) -> list[TagKey]:
        if not entities:
            return []
        self.db.add_all(entities)
        await self.db.flush()
        return entities


class TagValueRepository(BaseRepository[TagValue]):
    """Repository for tag values."""

    def __init__(self, db: AsyncSession):
        super().__init__(TagValue, db)

    async def list_by_tenant(self, tenant_id: int) -> list[TagValue]:
        result = await self.db.execute(select(TagValue).where(TagValue.tenant_id == tenant_id))
        return list(result.scalars().all())

    async def list_by_key(self, tenant_id: int, key_id: int) -> list[TagValue]:
        result = await self.db.execute(
            select(TagValue).where(TagValue.tenant_id == tenant_id, TagValue.key_id == key_id)
        )
        return list(result.scalars().all())

    async def get_by_id_and_tenant(self, tenant_id: int, tag_value_id: int) -> TagValue | None:
        result = await self.db.execute(
            select(TagValue).where(TagValue.tenant_id == tenant_id, TagValue.id == tag_value_id)
        )
        return result.scalar_one_or_none()

    async def get_by_key_and_rank(self, tenant_id: int, key_id: int, rank: int) -> TagValue | None:
        result = await self.db.execute(
            select(TagValue).where(
                TagValue.tenant_id == tenant_id,
                TagValue.key_id == key_id,
                TagValue.rank == rank,
            )
        )
        return result.scalar_one_or_none()

    async def create_many(self, entities: list[TagValue]) -> list[TagValue]:
        if not entities:
            return []
        self.db.add_all(entities)
        await self.db.flush()
        return entities


class TagBindingRepository(BaseRepository[TagBinding]):
    """Repository for tag bindings."""

    def __init__(self, db: AsyncSession):
        super().__init__(TagBinding, db)

    async def list_by_resource(self, tenant_id: int, resource_type: str, resource_id: int) -> list[TagBinding]:
        result = await self.db.execute(
            select(TagBinding).where(
                TagBinding.tenant_id == tenant_id,
                TagBinding.resource_type == resource_type,
                TagBinding.resource_id == resource_id,
            )
        )
        return list(result.scalars().all())

    async def list_by_resource_and_key(
        self,
        tenant_id: int,
        resource_type: str,
        resource_id: int,
        tag_key_id: int,
    ) -> list[TagBinding]:
        result = await self.db.execute(
            select(TagBinding)
            .join(TagValue, TagBinding.tag_value_id == TagValue.id)
            .where(
                TagBinding.tenant_id == tenant_id,
                TagBinding.resource_type == resource_type,
                TagBinding.resource_id == resource_id,
                TagValue.key_id == tag_key_id,
            )
        )
        return list(result.scalars().all())

    async def get_by_resource_and_tag_value(
        self,
        tenant_id: int,
        resource_type: str,
        resource_id: int,
        tag_value_id: int,
    ) -> TagBinding | None:
        result = await self.db.execute(
            select(TagBinding).where(
                TagBinding.tenant_id == tenant_id,
                TagBinding.resource_type == resource_type,
                TagBinding.resource_id == resource_id,
                TagBinding.tag_value_id == tag_value_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_tag_values_by_resource(
        self,
        tenant_id: int,
        resource_type: str,
        resource_id: int,
    ) -> list[TagValue]:
        result = await self.db.execute(
            select(TagValue)
            .join(TagBinding, TagBinding.tag_value_id == TagValue.id)
            .where(
                TagBinding.tenant_id == tenant_id,
                TagBinding.resource_type == resource_type,
                TagBinding.resource_id == resource_id,
            )
        )
        return list(result.scalars().all())

    async def list_by_tag_value(self, tenant_id: int, tag_value_id: int) -> list[TagBinding]:
        result = await self.db.execute(
            select(TagBinding).where(
                TagBinding.tenant_id == tenant_id,
                TagBinding.tag_value_id == tag_value_id,
            )
        )
        return list(result.scalars().all())


class ResourceTagConfigRepository(BaseRepository[ResourceTagConfig]):
    """Repository for resource tag whitelist configs."""

    def __init__(self, db: AsyncSession):
        super().__init__(ResourceTagConfig, db)

    async def list_by_tenant(self, tenant_id: int) -> list[ResourceTagConfig]:
        result = await self.db.execute(select(ResourceTagConfig).where(ResourceTagConfig.tenant_id == tenant_id))
        return list(result.scalars().all())

    async def list_by_resource_type(self, tenant_id: int, resource_type: str) -> list[ResourceTagConfig]:
        result = await self.db.execute(
            select(ResourceTagConfig).where(
                ResourceTagConfig.tenant_id == tenant_id,
                ResourceTagConfig.resource_type == resource_type,
            )
        )
        return list(result.scalars().all())

    async def get_by_id_and_tenant(self, tenant_id: int, config_id: int) -> ResourceTagConfig | None:
        result = await self.db.execute(
            select(ResourceTagConfig).where(
                ResourceTagConfig.tenant_id == tenant_id,
                ResourceTagConfig.id == config_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_by_resource_and_key(
        self,
        tenant_id: int,
        resource_type: str,
        tag_key_id: int,
    ) -> ResourceTagConfig | None:
        result = await self.db.execute(
            select(ResourceTagConfig).where(
                ResourceTagConfig.tenant_id == tenant_id,
                ResourceTagConfig.resource_type == resource_type,
                ResourceTagConfig.tag_key_id == tag_key_id,
            )
        )
        return result.scalar_one_or_none()

    async def create_many(self, entities: list[ResourceTagConfig]) -> list[ResourceTagConfig]:
        if not entities:
            return []
        self.db.add_all(entities)
        await self.db.flush()
        return entities
