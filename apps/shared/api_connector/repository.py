"""Repository layer for API connector resources."""

from __future__ import annotations

from sqlalchemy import String, and_, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.sql.elements import ColumnElement

from apps.shared.api_connector.constants import (
    OPERATION_SOURCE_IMPORTED,
    OPERATION_SOURCE_MANUAL,
    OPERATION_STATUS_ACTIVE,
    OPERATION_STATUS_DISABLED,
    OPERATION_STATUS_STALE,
)
from apps.shared.api_connector.domain import OperationStatus
from apps.shared.db.base_repository import BaseRepository
from apps.shared.db.models import ApiConnector, ApiOperationIndex


class ApiConnectorRepository(BaseRepository[ApiConnector]):
    """Data access for ApiConnector."""

    def __init__(self, db: AsyncSession):
        super().__init__(ApiConnector, db)

    async def get_by_id_and_tenant(self, connector_id: int, tenant_id: int) -> ApiConnector | None:
        result = await self.db.execute(
            select(ApiConnector)
            .options(selectinload(ApiConnector.owner_user))
            .where(ApiConnector.id == connector_id, ApiConnector.tenant_id == tenant_id)
        )
        return result.scalar_one_or_none()

    async def get_by_tenant_and_name(self, tenant_id: int, name: str) -> ApiConnector | None:
        result = await self.db.execute(
            select(ApiConnector).where(ApiConnector.tenant_id == tenant_id, ApiConnector.name == name)
        )
        return result.scalar_one_or_none()

    async def get_by_ids_and_tenant(
        self,
        connector_ids: list[int],
        tenant_id: int,
        scope_clause: ColumnElement[bool] | None = None,
    ) -> list[ApiConnector]:
        if not connector_ids:
            return []
        stmt = select(ApiConnector).options(selectinload(ApiConnector.owner_user)).where(
            ApiConnector.id.in_(connector_ids),
            ApiConnector.tenant_id == tenant_id,
        )
        if scope_clause is not None:
            stmt = stmt.where(scope_clause)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def list_by_tenant(
        self,
        tenant_id: int,
        scope_clause: ColumnElement[bool] | None = None,
    ) -> list[ApiConnector]:
        stmt = select(ApiConnector).options(selectinload(ApiConnector.owner_user)).where(
            ApiConnector.tenant_id == tenant_id
        )
        if scope_clause is not None:
            stmt = stmt.where(scope_clause)
        stmt = stmt.order_by(ApiConnector.created_at.desc())
        result = await self.db.execute(stmt)
        return list(result.scalars().all())


class ApiOperationIndexRepository(BaseRepository[ApiOperationIndex]):
    """Data access for ApiOperationIndex."""

    def __init__(self, db: AsyncSession):
        super().__init__(ApiOperationIndex, db)

    async def get_by_uid_and_tenant(self, operation_uid: str, tenant_id: int) -> ApiOperationIndex | None:
        result = await self.db.execute(
            select(ApiOperationIndex).where(
                ApiOperationIndex.operation_uid == operation_uid,
                ApiOperationIndex.tenant_id == tenant_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_by_connector(self, tenant_id: int, connector_id: int) -> list[ApiOperationIndex]:
        result = await self.db.execute(
            select(ApiOperationIndex)
            .where(
                ApiOperationIndex.tenant_id == tenant_id,
                ApiOperationIndex.connector_id == connector_id,
            )
            .order_by(ApiOperationIndex.method.asc(), ApiOperationIndex.path_template.asc())
        )
        return list(result.scalars().all())

    async def get_connector_operation_stats(
        self,
        *,
        tenant_id: int,
        connector_id: int,
    ) -> dict[str, int]:
        stmt = select(
            func.count(ApiOperationIndex.id).label("total"),
            func.count(ApiOperationIndex.id)
            .filter(ApiOperationIndex.status == OPERATION_STATUS_ACTIVE)
            .label("active"),
            func.count(ApiOperationIndex.id)
            .filter(ApiOperationIndex.status == OPERATION_STATUS_DISABLED)
            .label("disabled"),
            func.count(ApiOperationIndex.id)
            .filter(ApiOperationIndex.status == OPERATION_STATUS_STALE)
            .label("stale"),
            func.count(ApiOperationIndex.id)
            .filter(ApiOperationIndex.source == OPERATION_SOURCE_MANUAL)
            .label("manual"),
            func.count(ApiOperationIndex.id)
            .filter(ApiOperationIndex.source == OPERATION_SOURCE_IMPORTED)
            .label("imported"),
            func.count(func.distinct(ApiOperationIndex.path_template))
            .filter(
                and_(
                    ApiOperationIndex.source == OPERATION_SOURCE_IMPORTED,
                    ApiOperationIndex.status != OPERATION_STATUS_STALE,
                )
            )
            .label("path_count"),
        ).where(
            ApiOperationIndex.tenant_id == tenant_id,
            ApiOperationIndex.connector_id == connector_id,
        )
        result = await self.db.execute(stmt)
        row = result.one()
        return {
            "path_count": int(row.path_count or 0),
            "total": int(row.total or 0),
            "active": int(row.active or 0),
            "disabled": int(row.disabled or 0),
            "stale": int(row.stale or 0),
            "manual": int(row.manual or 0),
            "imported": int(row.imported or 0),
        }

    async def list_by_connector_paginated(
        self,
        *,
        tenant_id: int,
        connector_id: int,
        status: OperationStatus | None = None,
        limit: int,
        offset: int,
        query: str | None = None,
    ) -> list[ApiOperationIndex]:
        stmt = self._build_connector_list_stmt(
            tenant_id=tenant_id,
            connector_id=connector_id,
            status=status,
            query=query,
        )
        stmt = (
            stmt.order_by(ApiOperationIndex.method.asc(), ApiOperationIndex.path_template.asc())
            .offset(offset)
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def count_by_connector(
        self,
        *,
        tenant_id: int,
        connector_id: int,
        status: OperationStatus | None = None,
        query: str | None = None,
    ) -> int:
        stmt = self._build_connector_list_stmt(
            tenant_id=tenant_id,
            connector_id=connector_id,
            status=status,
            query=query,
        )
        count_stmt = stmt.with_only_columns(func.count(ApiOperationIndex.id)).order_by(None)
        result = await self.db.execute(count_stmt)
        return int(result.scalar() or 0)

    def _build_connector_list_stmt(
        self,
        *,
        tenant_id: int,
        connector_id: int,
        status: OperationStatus | None,
        query: str | None,
    ):
        stmt = select(ApiOperationIndex).where(
            ApiOperationIndex.tenant_id == tenant_id,
            ApiOperationIndex.connector_id == connector_id,
        )
        if status is not None:
            stmt = stmt.where(ApiOperationIndex.status == status)
        normalized_query = query.strip() if query else None
        if normalized_query:
            like = f"%{normalized_query}%"
            stmt = stmt.where(
                or_(
                    ApiOperationIndex.operation_id.ilike(like),
                    ApiOperationIndex.method.ilike(like),
                    ApiOperationIndex.summary.ilike(like),
                    ApiOperationIndex.description.ilike(like),
                    ApiOperationIndex.path_template.ilike(like),
                    cast(ApiOperationIndex.tags, String).ilike(like),
                )
            )
        return stmt

    async def list_imported_by_connector(self, tenant_id: int, connector_id: int) -> list[ApiOperationIndex]:
        result = await self.db.execute(
            select(ApiOperationIndex)
            .where(
                ApiOperationIndex.tenant_id == tenant_id,
                ApiOperationIndex.connector_id == connector_id,
                ApiOperationIndex.source == OPERATION_SOURCE_IMPORTED,
            )
            .order_by(ApiOperationIndex.updated_at.desc())
        )
        return list(result.scalars().all())

    async def get_by_id_and_tenant(self, operation_id: int, tenant_id: int) -> ApiOperationIndex | None:
        result = await self.db.execute(
            select(ApiOperationIndex).where(
                ApiOperationIndex.id == operation_id,
                ApiOperationIndex.tenant_id == tenant_id,
            )
        )
        return result.scalar_one_or_none()

    async def delete_by_connector(self, tenant_id: int, connector_id: int) -> None:
        result = await self.db.execute(
            select(ApiOperationIndex).where(
                ApiOperationIndex.tenant_id == tenant_id,
                ApiOperationIndex.connector_id == connector_id,
            )
        )
        rows = list(result.scalars().all())
        for row in rows:
            await self.db.delete(row)
        await self.db.flush()

    async def search(
        self,
        tenant_id: int,
        query: str | None = None,
        connector_id: int | None = None,
        scoped_connector_ids: list[int] | None = None,
        status: OperationStatus | None = OPERATION_STATUS_ACTIVE,
        limit: int = 20,
        offset: int = 0,
    ) -> list[ApiOperationIndex]:
        """Unified operation search with key-based filter.

        `scoped_connector_ids` must be the upstream authorization-filtered connector scope
        (ABAC/ACL filtered). This method only enforces that scope at SQL level.
        """
        normalized = query.strip() if query else ""
        if scoped_connector_ids is not None and not scoped_connector_ids:
            return []
        if connector_id is not None and scoped_connector_ids is not None and connector_id not in scoped_connector_ids:
            return []

        stmt = self._build_search_stmt(
            tenant_id=tenant_id,
            connector_id=connector_id,
            scoped_connector_ids=scoped_connector_ids,
            status=status,
            query=normalized,
        )
        paged_stmt = stmt.order_by(ApiOperationIndex.updated_at.desc()).offset(offset).limit(limit)
        result = await self.db.execute(paged_stmt)
        return list(result.scalars().all())

    async def count_search(
        self,
        *,
        tenant_id: int,
        query: str | None = None,
        connector_id: int | None = None,
        scoped_connector_ids: list[int] | None = None,
        status: OperationStatus | None = OPERATION_STATUS_ACTIVE,
    ) -> int:
        normalized = query.strip() if query else ""
        if scoped_connector_ids is not None and not scoped_connector_ids:
            return 0
        if connector_id is not None and scoped_connector_ids is not None and connector_id not in scoped_connector_ids:
            return 0

        stmt = self._build_search_stmt(
            tenant_id=tenant_id,
            connector_id=connector_id,
            scoped_connector_ids=scoped_connector_ids,
            status=status,
            query=normalized,
        )
        count_stmt = stmt.with_only_columns(func.count(ApiOperationIndex.id)).order_by(None)
        result = await self.db.execute(count_stmt)
        return int(result.scalar() or 0)

    def _build_search_stmt(
        self,
        *,
        tenant_id: int,
        connector_id: int | None,
        scoped_connector_ids: list[int] | None,
        status: OperationStatus | None,
        query: str | None = None,
    ):
        stmt = select(ApiOperationIndex).where(
            ApiOperationIndex.tenant_id == tenant_id,
        )
        if status is not None:
            stmt = stmt.where(ApiOperationIndex.status == status)
        if connector_id is not None:
            stmt = stmt.where(ApiOperationIndex.connector_id == connector_id)
        if scoped_connector_ids is not None:
            stmt = stmt.where(ApiOperationIndex.connector_id.in_(scoped_connector_ids))
        if query:
            like = f"%{query}%"
            stmt = stmt.where(
                or_(
                    ApiOperationIndex.operation_id.ilike(like),
                    ApiOperationIndex.method.ilike(like),
                    ApiOperationIndex.summary.ilike(like),
                    ApiOperationIndex.description.ilike(like),
                    ApiOperationIndex.path_template.ilike(like),
                    cast(ApiOperationIndex.tags, String).ilike(like),
                )
            )
        return stmt


    async def list_active_by_ids(
        self,
        *,
        tenant_id: int,
        operation_ids: list[int],
        scoped_connector_ids: list[int] | None = None,
        limit: int = 20,
    ) -> list[ApiOperationIndex]:
        if not operation_ids:
            return []
        if scoped_connector_ids is not None and not scoped_connector_ids:
            return []

        stmt = select(ApiOperationIndex).where(
            ApiOperationIndex.tenant_id == tenant_id,
            ApiOperationIndex.status == OPERATION_STATUS_ACTIVE,
            ApiOperationIndex.id.in_(operation_ids),
        )
        if scoped_connector_ids is not None:
            stmt = stmt.where(ApiOperationIndex.connector_id.in_(scoped_connector_ids))

        stmt = stmt.order_by(ApiOperationIndex.updated_at.desc()).limit(limit)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def list_active_by_tenant(self, tenant_id: int) -> list[ApiOperationIndex]:
        """List active operations for a tenant."""
        result = await self.db.execute(
            select(ApiOperationIndex)
            .where(
                ApiOperationIndex.tenant_id == tenant_id,
                ApiOperationIndex.status == OPERATION_STATUS_ACTIVE,
            )
            .order_by(ApiOperationIndex.updated_at.desc())
        )
        return list(result.scalars().all())

    async def count_active_by_tenant(self, tenant_id: int) -> int:
        """Count active operations for a tenant."""
        result = await self.db.execute(
            select(func.count(ApiOperationIndex.id)).where(
                ApiOperationIndex.tenant_id == tenant_id,
                ApiOperationIndex.status == OPERATION_STATUS_ACTIVE,
            )
        )
        return int(result.scalar() or 0)

    async def mark_sync_pending(self, operation_id: int) -> None:
        """Mark operation for vector indexing via ResourceIndex."""
        pass
