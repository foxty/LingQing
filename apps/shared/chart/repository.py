"""Chart resource persistence."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.db.models import Chart


class ChartRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(
        self,
        *,
        tenant_id: int,
        owner_id: int,
        thread_id: str,
        title: str,
    ) -> Chart:
        chart = Chart(
            tenant_id=tenant_id,
            owner_id=owner_id,
            thread_id=thread_id,
            title=title,
        )
        self.db.add(chart)
        await self.db.flush()
        await self.db.refresh(chart)
        return chart

    async def get_by_id(self, chart_id: int, *, tenant_id: int) -> Chart | None:
        stmt = select(Chart).where(Chart.id == chart_id, Chart.tenant_id == tenant_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
