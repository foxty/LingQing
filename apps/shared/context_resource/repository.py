"""Repository layer for context resource keyword search.

Performs simple ILIKE-based keyword matching across multiple resource tables.
No vector search, no FTS index — just lightweight prefix/suffix matching.
"""

from __future__ import annotations

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.context_resource.domain import ContextResourceItem, ContextResourceKey
from apps.shared.db.models import (
    AssetMetadata,
    Dashboard,
    DataSource,
    Document,
    LiveApp,
    Report,
    ScheduledTask,
)

# Maximum results per resource type before merging.
_DEFAULT_LIMIT_PER_TYPE = 10

_TYPE_TO_MODEL = {
    "document": Document,
    "dashboard": Dashboard,
    "report": Report,
    "scheduled_task": ScheduledTask,
    "app": LiveApp,
}


class ContextResourceRepository:
    """Keyword search across all context-capable resource tables."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    # ------------------------------------------------------------------
    # Public search entry point
    # ------------------------------------------------------------------

    async def search(
        self,
        tenant_id: int,
        query: str,
        limit_per_type: int = _DEFAULT_LIMIT_PER_TYPE,
    ) -> list[ContextResourceItem]:
        """Run keyword search across all resource types and merge results.

        Results are grouped by resource_type in the order they are queried.
        """
        results: list[ContextResourceItem] = []
        results.extend(await self._search_documents(tenant_id, query, limit_per_type))
        results.extend(await self._search_dashboards(tenant_id, query, limit_per_type))
        results.extend(await self._search_reports(tenant_id, query, limit_per_type))
        results.extend(await self._search_scheduled_tasks(tenant_id, query, limit_per_type))
        results.extend(await self._search_live_apps(tenant_id, query, limit_per_type))
        results.extend(await self._search_assets(tenant_id, query, limit_per_type))
        return results

    async def resolve_by_refs(
        self,
        tenant_id: int,
        refs: list[ContextResourceKey],
    ) -> list[ContextResourceItem]:
        """Resolve type/id refs to display metadata for chat history and agent context."""
        items: list[ContextResourceItem] = []
        for ref in refs:
            if ref.resource_type == "asset":
                items.append(await self._resolve_asset(tenant_id, ref.resource_id))
                continue

            model_cls = _TYPE_TO_MODEL.get(ref.resource_type)
            if model_cls is None:
                items.append(
                    ContextResourceItem(
                        resource_type=ref.resource_type,
                        resource_id=ref.resource_id,
                        title=f"Unknown {ref.resource_type}",
                    )
                )
                continue

            items.append(await self._resolve_typed_resource(tenant_id, ref, model_cls))

        return items

    async def _resolve_asset(self, tenant_id: int, resource_id: int) -> ContextResourceItem:
        stmt = (
            select(AssetMetadata, DataSource.name)
            .join(DataSource, AssetMetadata.data_source_id == DataSource.id)
            .where(
                AssetMetadata.id == resource_id,
                DataSource.tenant_id == tenant_id,
            )
        )
        result = await self._db.execute(stmt)
        row = result.one_or_none()
        if not row:
            return self._not_found_item("asset", resource_id)

        asset, data_source_name = row
        return ContextResourceItem(
            resource_type="asset",
            resource_id=resource_id,
            title=asset.asset_name,
            subtitle=data_source_name,
        )

    async def _resolve_typed_resource(
        self,
        tenant_id: int,
        ref: ContextResourceKey,
        model_cls: type,
    ) -> ContextResourceItem:
        stmt = select(model_cls).where(
            model_cls.id == ref.resource_id,
            model_cls.tenant_id == tenant_id,
        )
        result = await self._db.execute(stmt)
        row = result.scalar_one_or_none()
        if not row:
            return self._not_found_item(ref.resource_type, ref.resource_id)

        title = getattr(row, "title", None) or getattr(row, "name", None) or getattr(
            row, "filename", None
        ) or str(ref.resource_id)
        return ContextResourceItem(
            resource_type=ref.resource_type,
            resource_id=ref.resource_id,
            title=title,
        )

    @staticmethod
    def _not_found_item(resource_type: str, resource_id: int) -> ContextResourceItem:
        return ContextResourceItem(
            resource_type=resource_type,
            resource_id=resource_id,
            title=f"{resource_type} #{resource_id}",
            subtitle="not found",
        )

    # ------------------------------------------------------------------
    # Per-type keyword queries
    # ------------------------------------------------------------------

    async def _search_documents(
        self, tenant_id: int, query: str, limit: int
    ) -> list[ContextResourceItem]:
        stmt = (
            select(Document.id, Document.filename)
            .where(Document.tenant_id == tenant_id)
            .where(Document.filename.ilike(f"%{query}%"))
            .order_by(Document.filename)
            .limit(limit)
        )
        rows = await self._db.execute(stmt)
        return [
            ContextResourceItem(
                resource_type="document",
                resource_id=row[0],
                title=row[1],
            )
            for row in rows.all()
        ]

    async def _search_dashboards(
        self, tenant_id: int, query: str, limit: int
    ) -> list[ContextResourceItem]:
        stmt = (
            select(Dashboard.id, Dashboard.name)
            .where(Dashboard.tenant_id == tenant_id)
            .where(Dashboard.name.ilike(f"%{query}%"))
            .order_by(Dashboard.name)
            .limit(limit)
        )
        rows = await self._db.execute(stmt)
        return [
            ContextResourceItem(
                resource_type="dashboard",
                resource_id=row[0],
                title=row[1],
            )
            for row in rows.all()
        ]

    async def _search_reports(
        self, tenant_id: int, query: str, limit: int
    ) -> list[ContextResourceItem]:
        stmt = (
            select(Report.id, Report.title)
            .where(Report.tenant_id == tenant_id)
            .where(Report.title.ilike(f"%{query}%"))
            .order_by(Report.title)
            .limit(limit)
        )
        rows = await self._db.execute(stmt)
        return [
            ContextResourceItem(
                resource_type="report",
                resource_id=row[0],
                title=row[1],
            )
            for row in rows.all()
        ]

    async def _search_scheduled_tasks(
        self, tenant_id: int, query: str, limit: int
    ) -> list[ContextResourceItem]:
        stmt = (
            select(ScheduledTask.id, ScheduledTask.name)
            .where(ScheduledTask.tenant_id == tenant_id)
            .where(ScheduledTask.stable_key.is_(None))
            .where(ScheduledTask.name.ilike(f"%{query}%"))
            .order_by(ScheduledTask.name)
            .limit(limit)
        )
        rows = await self._db.execute(stmt)
        return [
            ContextResourceItem(
                resource_type="scheduled_task",
                resource_id=row[0],
                title=row[1],
            )
            for row in rows.all()
        ]

    async def _search_live_apps(
        self, tenant_id: int, query: str, limit: int
    ) -> list[ContextResourceItem]:
        stmt = (
            select(LiveApp.id, LiveApp.name)
            .where(LiveApp.tenant_id == tenant_id)
            .where(LiveApp.name.ilike(f"%{query}%"))
            .order_by(LiveApp.name)
            .limit(limit)
        )
        rows = await self._db.execute(stmt)
        return [
            ContextResourceItem(
                resource_type="app",
                resource_id=row[0],
                title=row[1],
            )
            for row in rows.all()
        ]

    async def _search_assets(
        self, tenant_id: int, query: str, limit: int
    ) -> list[ContextResourceItem]:
        """Search data source assets by asset_name.

        Includes the data source name as subtitle for disambiguation.
        """
        stmt = text("""
            SELECT am.id, am.asset_name, ds.name AS ds_name
            FROM asset_metadata am
            JOIN data_sources ds ON ds.id = am.data_source_id
            WHERE ds.tenant_id = :tenant_id
              AND am.asset_name ILIKE :pattern
            ORDER BY am.asset_name
            LIMIT :lim
        """)
        result = await self._db.execute(
            stmt,
            {"tenant_id": tenant_id, "pattern": f"%{query}%", "lim": limit},
        )
        return [
            ContextResourceItem(
                resource_type="asset",
                resource_id=row[0],
                title=row[1],
                subtitle=row[2],
            )
            for row in result.all()
        ]
