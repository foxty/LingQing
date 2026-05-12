"""Resource Index Repository - CRUD for resource_index table."""

from datetime import UTC, datetime

from sqlalchemy import case, func, literal_column, or_, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.db.base_repository import BaseRepository
from apps.shared.db.models import Document, ResourceIndex
from apps.shared.domain.types import RESOURCE_TYPE_API_CONNECTOR, RESOURCE_TYPE_ASSET, RESOURCE_TYPE_DOCUMENT
from apps.shared.search.domain import VectorStatus
from apps.shared.search.parser import unified_tokenize
from apps.shared.utils.logger import get_logger

logger = get_logger(__name__)

# Vector statuses that need processing
STATUSES_NEED_INDEXING = ("pending", "stale", "failed")


class ResourceIndexRepository(BaseRepository[ResourceIndex]):
    """Repository for resource_index table operations.

    Provides:
    - CRUD for resource index records
    - FTS search across all resource types
    - Status-based queries for scheduler
    - Batch operations for embedding model changes
    - Sync status tracking
    """

    def __init__(self, db: AsyncSession):
        super().__init__(ResourceIndex, db)

    # ==================== Core Queries ====================

    async def get_by_resource(self, tenant_id: int, resource_type: str, resource_id: int) -> ResourceIndex | None:
        """Get resource index by tenant, type, and resource ID."""
        stmt = select(ResourceIndex).where(
            ResourceIndex.tenant_id == tenant_id,
            ResourceIndex.resource_type == resource_type,
            ResourceIndex.resource_id == resource_id,
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_resources(
        self,
        tenant_id: int,
        resource_type: str,
        resource_ids: list[int],
    ) -> dict[int, ResourceIndex]:
        """Batch fetch resource index records by resource IDs.

        Args:
            tenant_id: Tenant ID
            resource_type: Resource type (e.g., 'document', 'asset')
            resource_ids: List of resource IDs

        Returns:
            Dict mapping resource_id to ResourceIndex
        """
        if not resource_ids:
            return {}

        stmt = select(ResourceIndex).where(
            ResourceIndex.tenant_id == tenant_id,
            ResourceIndex.resource_type == resource_type,
            ResourceIndex.resource_id.in_(resource_ids),
        )
        result = await self.db.execute(stmt)
        records = result.scalars().all()
        return {ri.resource_id: ri for ri in records}

    async def list_by_statuses(
        self,
        tenant_id: int,
        statuses: list[str],
        limit: int = 50,
    ) -> list[ResourceIndex]:
        """List records with given statuses for scheduler processing.

        Returns records sorted by content_updated_at ASC (oldest first).
        Only returns records where vector_next_retry_at is NULL or <= NOW (backoff expired).
        Retry eligibility is controlled by vector_next_retry_at, not retry count.
        Records without raw_content are skipped — they are waiting for parse, not vector sync.
        """
        now = datetime.now(UTC)
        stmt = (
            select(ResourceIndex)
            .where(
                ResourceIndex.tenant_id == tenant_id,
                ResourceIndex.vector_status.in_(statuses),
                ResourceIndex.raw_content.isnot(None),
                or_(
                    ResourceIndex.vector_next_retry_at.is_(None),
                    ResourceIndex.vector_next_retry_at <= now,
                ),
            )
            .order_by(ResourceIndex.content_updated_at.asc())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def list_all_by_tenant(
        self,
        tenant_id: int,
        status: str | None = None,
        resource_type: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[ResourceIndex]:
        """List all resource index records for a tenant."""
        stmt = select(ResourceIndex).where(ResourceIndex.tenant_id == tenant_id)
        if status:
            stmt = stmt.where(ResourceIndex.vector_status == status)
        if resource_type:
            stmt = stmt.where(ResourceIndex.resource_type == resource_type)
        stmt = stmt.order_by(ResourceIndex.created_at.desc())
        if offset:
            stmt = stmt.offset(offset)
        if limit:
            stmt = stmt.limit(limit)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def count_by_tenant(
        self,
        tenant_id: int,
        status: str | None = None,
        resource_type: str | None = None,
    ) -> int:
        """Count resource index records for a tenant."""
        stmt = select(func.count()).where(ResourceIndex.tenant_id == tenant_id)
        if status:
            stmt = stmt.where(ResourceIndex.vector_status == status)
        if resource_type:
            stmt = stmt.where(ResourceIndex.resource_type == resource_type)
        result = await self.db.execute(stmt)
        return int(result.scalar_one() or 0)

    async def get_resource_ids_by_type(self, tenant_id: int, resource_type: str) -> set[int]:
        """Get all resource IDs for a given resource type from the resource_index table.

        Used for orphan detection by comparing resource_index IDs against source DB IDs.
        """
        stmt = select(ResourceIndex.resource_id).where(
            ResourceIndex.tenant_id == tenant_id,
            ResourceIndex.resource_type == resource_type,
        )
        result = await self.db.execute(stmt)
        return {row[0] for row in result.all() if row[0] is not None}

    # ==================== FTS Search Methods ====================

    async def search_fts(
        self,
        tenant_id: int,
        query: str,
        resource_types: list[str] | None = None,
        limit: int = 20,
    ) -> list[tuple[ResourceIndex, float]]:
        """Full-text search across resource index records.

        Uses jieba tokenization with 'simple' config for Chinese/English support.
        Returns list of (ResourceIndex, rank) tuples sorted by relevance.

        Args:
            tenant_id: Tenant ID scope
            query: Search query text
            resource_types: Optional filter by resource types
            limit: Maximum results

        Returns:
            List of (ResourceIndex, rank) tuples
        """
        tokenized_query = unified_tokenize(query)
        tsquery = func.plainto_tsquery("simple", tokenized_query)
        fts_tsvector = literal_column("fts_content_tsvector")
        rank = func.ts_rank(fts_tsvector, tsquery)

        stmt = (
            select(ResourceIndex, rank)
            .where(
                ResourceIndex.tenant_id == tenant_id,
                fts_tsvector.op("@@", is_comparison=True)(tsquery),
            )
            .order_by(rank.desc())
            .limit(limit)
        )
        if resource_types:
            stmt = stmt.where(ResourceIndex.resource_type.in_(resource_types))

        result = await self.db.execute(stmt)
        return [(row[0], float(row[1] or 0)) for row in result.all()]

    async def search_documents_fts(
        self,
        tenant_id: int,
        query: str,
        limit: int = 20,
        abac_filter=None,
    ) -> list[tuple[ResourceIndex, float, str | None]]:
        """FTS search specifically for document resources with snippet.

        Returns:
            List of (ResourceIndex, rank, snippet) tuples where snippet is
            the highlighted matching text from ts_headline.
        """
        stmt = self._build_fts_query(tenant_id, query, RESOURCE_TYPE_DOCUMENT, limit, abac_filter, include_snippet=True)
        return await self._execute_fts_query(stmt)

    async def search_assets_fts(
        self,
        tenant_id: int,
        query: str,
        limit: int = 20,
        abac_filter=None,
        parent_ids: list[int] | None = None,
    ) -> list[tuple[ResourceIndex, float]]:
        """FTS search specifically for asset resources."""
        stmt = self._build_fts_query(tenant_id, query, RESOURCE_TYPE_ASSET, limit, abac_filter, parent_ids)
        return await self._execute_fts_query(stmt)

    async def search_api_operations_fts(
        self,
        tenant_id: int,
        query: str,
        limit: int = 20,
        abac_filter=None,
        parent_ids: list[int] | None = None,
    ) -> list[tuple[ResourceIndex, float]]:
        """FTS search specifically for API operation resources."""
        stmt = self._build_fts_query(tenant_id, query, RESOURCE_TYPE_API_CONNECTOR, limit, abac_filter, parent_ids)
        return await self._execute_fts_query(stmt)

    def _build_fts_query(
        self,
        tenant_id: int,
        query: str,
        resource_type: str,
        limit: int,
        abac_filter=None,
        parent_ids: list[int] | None = None,
        include_snippet: bool = False,
    ):
        """Build a parameterized FTS query for a specific resource type.

        Uses jieba tokenization with PostgreSQL 'simple' config for Chinese/English FTS.
        The 'simple' config does no stemming, just splits on whitespace - perfect for jieba output.

        Args:
            tenant_id: Tenant scope
            query: Search query (will be tokenized with jieba)
            resource_type: document, asset, or api_connector
            limit: Max results
            abac_filter: Optional ABAC/ACL SQL filter clause
            parent_ids: Optional parent ID filter (data_source_id for assets, connector_id for api_operations)
            include_snippet: Whether to include ts_headline snippet in results
        """
        tokenized_query = unified_tokenize(query)
        tsquery = func.plainto_tsquery("simple", tokenized_query)
        fts_tsvector = literal_column("fts_content_tsvector")
        rank = func.ts_rank(fts_tsvector, tsquery)

        conditions = [
            ResourceIndex.tenant_id == tenant_id,
            ResourceIndex.resource_type == resource_type,
            fts_tsvector.op("@@", is_comparison=True)(tsquery),
        ]
        if abac_filter is not None:
            conditions.append(abac_filter)
        if parent_ids is not None:
            conditions.append(ResourceIndex.parent_id.in_(parent_ids))

        if include_snippet:
            # Generate highlighted snippet using ts_headline
            snippet = func.ts_headline(
                "simple",
                ResourceIndex.tokenized_content,
                tsquery,
                text("'StartSel=<mark>,StopSel=</mark>,MaxWords=100,MinWords=10'"),
            )
            stmt = select(ResourceIndex, rank, snippet).where(*conditions).order_by(rank.desc()).limit(limit)
        else:
            stmt = select(ResourceIndex, rank).where(*conditions).order_by(rank.desc()).limit(limit)
        return stmt

    async def _execute_fts_query(self, stmt) -> list[tuple[ResourceIndex, float, str | None]]:
        """Execute an FTS query and return (ResourceIndex, rank, snippet) tuples."""
        result = await self.db.execute(stmt)
        rows = result.all()
        # Check if snippet is included (3 columns) or not (2 columns)
        if len(rows) > 0 and len(rows[0]) == 3:
            return [(row[0], float(row[1] or 0), row[2]) for row in rows]
        return [(row[0], float(row[1] or 0), None) for row in rows]

    # ==================== Sync Status Operations ====================

    async def mark_vector_indexing(self, record_id: int) -> None:
        """Mark record as being indexed (prevent concurrent processing)."""
        await self.db.execute(
            update(ResourceIndex)
            .where(ResourceIndex.id == record_id)
            .values(
                vector_status=VectorStatus.INDEXING,
            ),
            execution_options={"synchronize_session": False},
        )

    async def mark_vector_synced(self, record_id: int, content_hash: str | None = None) -> None:
        """Mark record as successfully synced to VectorDB."""
        await self.db.execute(
            update(ResourceIndex)
            .where(ResourceIndex.id == record_id)
            .values(
                vector_status=VectorStatus.INDEXED,
                vector_content_hash=content_hash,
                vector_synced_at=datetime.now(UTC),
                vector_sync_error_at=None,
                vector_sync_error=None,
            ),
            execution_options={"synchronize_session": False},
        )

    async def mark_vector_failed(
        self,
        record_id: int,
        error: str,
        increment_retry: bool = True,
    ) -> None:
        """Mark record as failed to sync."""
        values: dict = {
            "vector_status": VectorStatus.FAILED,
            "vector_sync_error_at": datetime.now(UTC),
            "vector_sync_error": error[:1000],
        }
        if increment_retry:
            values["vector_retry_count"] = ResourceIndex.vector_retry_count + 1
        await self.db.execute(
            update(ResourceIndex).where(ResourceIndex.id == record_id).values(values),
            execution_options={"synchronize_session": False},
        )

    async def update_vector_synced(
        self, record_id: int, *, vector_content_hash: str | None = None, tokenized_content: str | None = None
    ) -> None:
        """Mark record as successfully synced with tokenized content for FTS."""
        values = {
            "vector_status": VectorStatus.INDEXED,
            "vector_content_hash": vector_content_hash,
            "vector_synced_at": datetime.now(UTC),
            "vector_sync_error_at": None,
            "vector_sync_error": None,
            "vector_retry_count": 0,
        }
        if tokenized_content is not None:
            values["tokenized_content"] = tokenized_content

        await self.db.execute(
            update(ResourceIndex).where(ResourceIndex.id == record_id).values(values),
            execution_options={"synchronize_session": False},
        )

    async def update_vector_failed(self, record_id: int, error: str, next_retry_at: datetime | None = None) -> None:
        """Mark record as failed to sync, increment retry count.

        Args:
            record_id: Resource index record ID
            error: Error message
            next_retry_at: When to allow next retry (calculated by service layer)
        """
        await self.db.execute(
            update(ResourceIndex)
            .where(ResourceIndex.id == record_id)
            .values(
                vector_status=VectorStatus.FAILED,
                vector_sync_error_at=datetime.now(UTC),
                vector_sync_error=error[:1000],
                vector_retry_count=ResourceIndex.vector_retry_count + 1,
                vector_next_retry_at=next_retry_at,
            ),
            execution_options={"synchronize_session": False},
        )

    async def mark_vector_permanent_failed(self, record_id: int, error: str) -> None:
        """Mark record as permanently failed (no more retries)."""
        await self.db.execute(
            update(ResourceIndex)
            .where(ResourceIndex.id == record_id)
            .values(
                vector_status=VectorStatus.PERMANENT_FAILED,
                vector_sync_error_at=datetime.now(UTC),
                vector_sync_error=error[:1000],
            ),
            execution_options={"synchronize_session": False},
        )

    async def mark_vector_stale(self, record_id: int) -> None:
        """Mark record as stale (needs re-indexing due to content change)."""
        await self.db.execute(
            update(ResourceIndex)
            .where(ResourceIndex.id == record_id)
            .values(
                vector_status=VectorStatus.STALE,
                content_updated_at=datetime.now(UTC),
            ),
            execution_options={"synchronize_session": False},
        )

    async def mark_document_vector_stale(self, tenant_id: int, document_id: int) -> bool:
        """Mark a single document for vector re-indexing. Returns False if not eligible."""
        record = await self.get_by_resource(tenant_id, RESOURCE_TYPE_DOCUMENT, document_id)
        if record is None or record.raw_content is None:
            return False
        if record.vector_status == VectorStatus.PERMANENT_FAILED:
            return False

        await self.db.execute(
            update(ResourceIndex)
            .where(ResourceIndex.id == record.id)
            .values(
                vector_status=VectorStatus.STALE,
                content_updated_at=datetime.now(UTC),
                vector_retry_count=0,
                vector_sync_error=None,
                updated_at=datetime.now(UTC),
            ),
            execution_options={"synchronize_session": False},
        )
        return True

    async def mark_collection_vectors_stale(self, tenant_id: int, collection_id: int) -> int:
        """Mark all parsed documents in a collection for vector re-indexing."""
        result = await self.db.execute(
            update(ResourceIndex)
            .where(
                ResourceIndex.tenant_id == tenant_id,
                ResourceIndex.resource_type == RESOURCE_TYPE_DOCUMENT,
                ResourceIndex.raw_content.isnot(None),
                ResourceIndex.vector_status != VectorStatus.PERMANENT_FAILED,
                ResourceIndex.resource_id.in_(
                    select(Document.id).where(
                        Document.tenant_id == tenant_id,
                        Document.collection_id == collection_id,
                    )
                ),
            )
            .values(
                vector_status=VectorStatus.STALE,
                content_updated_at=datetime.now(UTC),
                vector_retry_count=0,
                vector_sync_error=None,
                updated_at=datetime.now(UTC),
            )
            .execution_options(synchronize_session=False)
        )
        return int(result.rowcount or 0)

    # ==================== Batch Operations ====================

    async def mark_all_vectors_stale(self, tenant_id: int) -> int:
        """Mark all vector records as stale for a tenant.

        Used when embedding model changes - all records need re-indexing.

        Returns:
            Number of records marked as stale.
        """
        result = await self.db.execute(
            update(ResourceIndex)
            .where(
                ResourceIndex.tenant_id == tenant_id,
                ResourceIndex.vector_status != VectorStatus.PERMANENT_FAILED,
            )
            .values(
                vector_status=VectorStatus.STALE,
                vector_retry_count=0,
            )
            .execution_options(synchronize_session=False)
        )
        return result.rowcount

    # ==================== Internal Helpers ====================

    @staticmethod
    def _update_query(record_id: int, fields: dict) -> object:
        """Build an UPDATE statement for a single record.

        Returns a SQLAlchemy Update construct ready for db.execute().
        """
        return update(ResourceIndex).where(ResourceIndex.id == record_id).values(**fields)

    async def upsert(
        self,
        tenant_id: int,
        resource_type: str,
        resource_id: int,
        owner_id: int,
        raw_content: dict | None,
        content_updated_at: datetime,
        parent_id: int | None = None,
        source_parser: str = "default",
    ) -> ResourceIndex:
        """Create or update a resource index record.

        Flow 1: Store raw_content from parser. Tokenization happens in Flow 2.

        Status logic:
        - New record: vector_status = "pending"
        - Existing with changed raw_content: vector_status = "stale"
        - Existing with unchanged raw_content: keep current status

        Returns the persisted ResourceIndex instance (refreshed).
        """
        import json

        existing = await self.get_by_resource(tenant_id, resource_type, resource_id)
        now = datetime.now(UTC)

        if existing:
            vector_status = existing.vector_status
            update_fields: dict = {
                "content_updated_at": content_updated_at,
                "updated_at": now,
                "owner_id": owner_id,
                "parent_id": parent_id,
                "source_parser": source_parser,
            }
            if raw_content is not None:
                existing_raw = existing.raw_content or {}
                if json.dumps(existing_raw, sort_keys=True) != json.dumps(raw_content, sort_keys=True):
                    vector_status = VectorStatus.STALE
                update_fields["raw_content"] = raw_content
            update_fields["vector_status"] = vector_status

            await self.db.execute(
                update(ResourceIndex).where(ResourceIndex.id == existing.id).values(**update_fields),
                execution_options={"synchronize_session": False},
            )
            await self.db.flush()
            await self.db.refresh(existing)
            return existing

        new_record = ResourceIndex(
            tenant_id=tenant_id,
            resource_type=resource_type,
            resource_id=resource_id,
            owner_id=owner_id,
            parent_id=parent_id,
            raw_content=raw_content,
            vector_status=VectorStatus.PENDING,
            content_updated_at=content_updated_at,
            source_parser=source_parser,
        )
        self.db.add(new_record)
        await self.db.flush()
        await self.db.refresh(new_record)
        return new_record

    async def mark_stale_if_changed(
        self,
        tenant_id: int,
        resource_type: str,
        resource_id: int,
        raw_content: dict | None = None,
    ) -> ResourceIndex | None:
        """Mark vector as stale if content has changed.

        Returns the updated record, or None if not found.
        """
        record = await self.get_by_resource(tenant_id, resource_type, resource_id)
        if not record:
            return None

        now = datetime.now(UTC)
        update_fields: dict = {"content_updated_at": now, "updated_at": now}
        if raw_content is not None:
            update_fields["raw_content"] = raw_content

        if raw_content is not None and record.raw_content != raw_content:
            update_fields["vector_status"] = VectorStatus.STALE

        await self.db.execute(
            update(ResourceIndex).where(ResourceIndex.id == record.id).values(update_fields),
            execution_options={"synchronize_session": False},
        )
        await self.db.flush()
        await self.db.refresh(record)
        return record

    # ==================== Parse Lifecycle Operations ====================

    async def update_parse_submitted(
        self,
        tenant_id: int,
        resource_type: str,
        resource_id: int,
        *,
        parse_job_id: str,
        source_parser: str,
    ) -> None:
        await self.db.execute(
            update(ResourceIndex)
            .where(
                ResourceIndex.tenant_id == tenant_id,
                ResourceIndex.resource_type == resource_type,
                ResourceIndex.resource_id == resource_id,
            )
            .values(
                parse_job_id=parse_job_id,
                source_parser=source_parser,
                parse_error=None,
                parse_error_at=None,
                updated_at=datetime.now(UTC),
            ),
            execution_options={"synchronize_session": False},
        )

    async def update_parse_completed(
        self,
        tenant_id: int,
        resource_type: str,
        resource_id: int,
        *,
        parsed_at: datetime,
    ) -> None:
        await self.db.execute(
            update(ResourceIndex)
            .where(
                ResourceIndex.tenant_id == tenant_id,
                ResourceIndex.resource_type == resource_type,
                ResourceIndex.resource_id == resource_id,
            )
            .values(
                parsed_at=parsed_at,
                parse_job_id=None,
                parse_error=None,
                parse_error_at=None,
                parse_retry_count=0,
                updated_at=datetime.now(UTC),
            ),
            execution_options={"synchronize_session": False},
        )

    async def update_parse_failed(
        self,
        tenant_id: int,
        resource_type: str,
        resource_id: int,
        *,
        error: str,
        parse_error_at: datetime,
    ) -> None:
        await self.db.execute(
            update(ResourceIndex)
            .where(
                ResourceIndex.tenant_id == tenant_id,
                ResourceIndex.resource_type == resource_type,
                ResourceIndex.resource_id == resource_id,
            )
            .values(
                parse_error=error[:1000],
                parse_error_at=parse_error_at,
                parse_job_id=None,
                parse_retry_count=ResourceIndex.parse_retry_count + 1,
                updated_at=datetime.now(UTC),
            ),
            execution_options={"synchronize_session": False},
        )

    async def reset_parse_state(
        self,
        tenant_id: int,
        resource_type: str,
        resource_id: int,
    ) -> None:
        await self.db.execute(
            update(ResourceIndex)
            .where(
                ResourceIndex.tenant_id == tenant_id,
                ResourceIndex.resource_type == resource_type,
                ResourceIndex.resource_id == resource_id,
            )
            .values(
                parse_job_id=None,
                parsed_at=None,
                parse_error=None,
                parse_error_at=None,
                parse_retry_count=0,
                raw_content=None,
                updated_at=datetime.now(UTC),
            ),
            execution_options={"synchronize_session": False},
        )

    async def list_pending_parse_jobs(self, tenant_id: int, limit: int = 10) -> list[ResourceIndex]:
        stmt = (
            select(ResourceIndex)
            .where(
                ResourceIndex.tenant_id == tenant_id,
                ResourceIndex.resource_type == RESOURCE_TYPE_DOCUMENT,
                ResourceIndex.parse_job_id.isnot(None),
                ResourceIndex.parsed_at.is_(None),
                ResourceIndex.parse_error_at.is_(None),
            )
            .order_by(ResourceIndex.updated_at.asc())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def document_parse_status_by_tenant(self, tenant_id: int) -> list[dict]:
        stmt = select(
            func.count(ResourceIndex.id).label("total"),
            func.sum(case((ResourceIndex.parsed_at.isnot(None), 1), else_=0)).label("parsed"),
            func.sum(
                case(
                    (
                        ResourceIndex.parse_job_id.isnot(None)
                        & ResourceIndex.parsed_at.is_(None)
                        & ResourceIndex.parse_error_at.is_(None),
                        1,
                    ),
                    else_=0,
                )
            ).label("async_pending"),
            func.sum(case((ResourceIndex.parse_error.isnot(None), 1), else_=0)).label("parse_errors"),
            func.max(ResourceIndex.parsed_at).label("last_parsed_at"),
        ).where(
            ResourceIndex.tenant_id == tenant_id,
            ResourceIndex.resource_type == RESOURCE_TYPE_DOCUMENT,
        )
        row = (await self.db.execute(stmt)).one()
        if not row.total:
            return []
        return [
            {
                "tenant_id": tenant_id,
                "total": int(row.total or 0),
                "parsed": int(row.parsed or 0),
                "async_pending": int(row.async_pending or 0),
                "parse_errors": int(row.parse_errors or 0),
                "last_parsed_at": row.last_parsed_at,
            }
        ]

    async def document_vector_status_by_tenant(self, tenant_id: int) -> list[tuple[str, int]]:
        stmt = (
            select(ResourceIndex.vector_status, func.count(ResourceIndex.id))
            .where(
                ResourceIndex.tenant_id == tenant_id,
                ResourceIndex.resource_type == RESOURCE_TYPE_DOCUMENT,
            )
            .group_by(ResourceIndex.vector_status)
        )
        result = await self.db.execute(stmt)
        return [(row[0], row[1]) for row in result.all()]

    async def delete_by_resource(self, tenant_id: int, resource_type: str, resource_id: int) -> bool:
        """Delete resource index record."""
        result = await self.db.execute(
            select(ResourceIndex).where(
                ResourceIndex.tenant_id == tenant_id,
                ResourceIndex.resource_type == resource_type,
                ResourceIndex.resource_id == resource_id,
            )
        )
        record = result.scalar_one_or_none()
        if record:
            await self.db.delete(record)
            await self.db.flush()
            return True
        return False
