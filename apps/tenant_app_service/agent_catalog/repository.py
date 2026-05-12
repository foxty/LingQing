"""Repository for custom agents."""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from apps.shared.db.base_repository import BaseRepository
from apps.shared.db.models import Agent


class AgentCatalogRepository(BaseRepository[Agent]):
    def __init__(self, db: AsyncSession):
        super().__init__(Agent, db)

    async def get_by_id_and_tenant(self, agent_id: int, tenant_id: int) -> Agent | None:
        result = await self.db.execute(select(Agent).where(Agent.id == agent_id, Agent.tenant_id == tenant_id))
        return result.scalar_one_or_none()

    async def get_by_name(self, tenant_id: int, name: str) -> Agent | None:
        result = await self.db.execute(select(Agent).where(Agent.tenant_id == tenant_id, Agent.name == name))
        return result.scalar_one_or_none()

    async def list_for_tenant(
        self,
        tenant_id: int,
        *,
        scope_clause: ColumnElement[bool] | None = None,
    ) -> list[Agent]:
        stmt = select(Agent).where(Agent.tenant_id == tenant_id, Agent.status == "active")
        if scope_clause is not None:
            stmt = stmt.where(scope_clause)
        stmt = stmt.order_by(Agent.updated_at.desc())
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def count_active(self, tenant_id: int) -> int:
        result = await self.db.execute(
            select(func.count()).select_from(Agent).where(Agent.tenant_id == tenant_id, Agent.status == "active")
        )
        return int(result.scalar_one() or 0)
