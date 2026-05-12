"""Service layer for context resource keyword search."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.context_resource.domain import ContextResourceItem, ContextResourceKey
from apps.shared.context_resource.repository import ContextResourceRepository


class ContextResourceSearchService:
    """Orchestrates keyword search across all context-capable resources."""

    def __init__(self, tenant_id: int, db_session: AsyncSession) -> None:
        self._tenant_id = tenant_id
        self._repo = ContextResourceRepository(db_session)

    async def search(self, query: str, limit: int = 10) -> list[ContextResourceItem]:
        """Return keyword-matched resources for the current tenant.

        Args:
            query: User-typed search term (already trimmed).
            limit: Max results per resource type.

        Returns:
            Flat list of ContextResourceItem, grouped by type.
        """
        return await self._repo.search(
            tenant_id=self._tenant_id,
            query=query,
            limit_per_type=limit,
        )

    async def resolve_by_refs(
        self,
        refs: list[ContextResourceKey],
    ) -> list[ContextResourceItem]:
        """Resolve @mention refs to tenant-scoped display metadata."""
        return await self._repo.resolve_by_refs(self._tenant_id, refs)
