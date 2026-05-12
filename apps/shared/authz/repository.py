"""Repository for ABAC policies."""

from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.db.base_repository import BaseRepository
from apps.shared.db.models import AbacPolicy


class AbacPolicyRepository(BaseRepository[AbacPolicy]):
    """Repository for ABAC policies."""

    def __init__(self, db: AsyncSession):
        super().__init__(AbacPolicy, db)

    async def list_by_tenant(self, tenant_id: int) -> list[AbacPolicy]:
        result = await self.db.execute(select(AbacPolicy).where(AbacPolicy.tenant_id == tenant_id))
        return list(result.scalars().all())

    async def list_by_resource_type(self, tenant_id: int, resource_type: str) -> list[AbacPolicy]:
        result = await self.db.execute(
            select(AbacPolicy).where(
                AbacPolicy.tenant_id == tenant_id,
                AbacPolicy.resource_type == resource_type,
            )
        )
        return list(result.scalars().all())

    async def list_by_resource_type_and_action(
        self,
        tenant_id: int,
        resource_type: str,
        action: str,
    ) -> list[AbacPolicy]:
        action_clause = AbacPolicy.action == action
        if action == "read":
            action_clause = or_(AbacPolicy.action == "read", AbacPolicy.action.is_(None))

        result = await self.db.execute(
            select(AbacPolicy).where(
                AbacPolicy.tenant_id == tenant_id,
                AbacPolicy.resource_type == resource_type,
                action_clause,
            )
        )
        return list(result.scalars().all())

    async def get_by_id_and_tenant(self, tenant_id: int, policy_id: int) -> AbacPolicy | None:
        result = await self.db.execute(
            select(AbacPolicy).where(AbacPolicy.tenant_id == tenant_id, AbacPolicy.id == policy_id)
        )
        return result.scalar_one_or_none()
