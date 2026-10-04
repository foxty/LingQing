"""Resource index service — ingest-side indexing and vector sync.

Owns ResourceIndex CRUD and drives vector/FTS synchronization. Query-time
hybrid search lives in :mod:`apps.shared.search.search_service`.

Flow 1 (upload/sync): Parse resource → save raw_content to ResourceIndex
Flow 2 (sync job): Read raw_content → tokenize + chunk → save to FTS + Vector DB
"""

import hashlib
import json
import time
from datetime import UTC, datetime, timedelta
from typing import Any

from langchain_core.documents import Document
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.data_source.repository import AssetMetadataRepository
from apps.shared.db.models import Document as DocumentModel
from apps.shared.document.manifest import get_storage_uri, is_manifest_pointer, read_blocks_json
from apps.shared.domain.types import (
    SearchableResourceType,
)
from apps.shared.llm_providers.embedding_resolver import resolve_tenant_embeddings
from apps.shared.infra.rag.index_payload import IndexRecordPayload, IndexUpsertPayload
from apps.shared.infra.rag.metadata_keys import (
    META_CHUNK_INDEX,
    META_OWNER_ID,
    META_PARENT_ID,
    META_RESOURCE_ID,
    META_RESOURCE_TYPE,
    META_TENANT_ID,
    META_TOTAL_CHUNKS,
)
from apps.shared.infra.rag.rag_manager import RAGManager
from apps.shared.infra.storage import FileStorage
from apps.shared.search.adapters import db_to_domain, domain_to_response
from apps.shared.search.parser import ResourceParser
from apps.shared.search.repository import ResourceIndexRepository
from apps.shared.search.schemas import (
    ResourceIndexCreateDTO,
    ResourceIndexPendingItem,
    ResourceIndexResponse,
)
from apps.shared.utils.logger import get_logger

logger = get_logger(__name__)


def _compute_content_hash(content: str) -> str:
    """Compute SHA256 hash of content string."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


class ResourceIndexService:
    """Service for resource index CRUD and vector sync scheduling.

    Design:
    - Accepts DTOs, converts to domain models
    - Orchestrates repository operations
    - Handles content change detection for stale marking
    - Drives vector/FTS synchronization from ResourceIndex records
    """

    def __init__(
        self,
        tenant_id: int,
        db_session: AsyncSession,
        embeddings=None,
        file_storage: FileStorage | None = None,
    ):
        self.tenant_id = tenant_id
        self.db_session = db_session
        self.file_storage = file_storage

        self._repo = ResourceIndexRepository(db_session)
        self.asset_repo = AssetMetadataRepository(db_session)
        self._embeddings = embeddings
        self.rag_manager = RAGManager(tenant_id=tenant_id, embeddings=embeddings)

    @classmethod
    async def create(
        cls,
        tenant_id: int,
        db_session: AsyncSession,
        *,
        file_storage: FileStorage | None = None,
    ) -> "ResourceIndexService":
        embeddings = await resolve_tenant_embeddings(tenant_id, db_session)
        return cls(
            tenant_id=tenant_id,
            db_session=db_session,
            embeddings=embeddings,
            file_storage=file_storage,
        )

    # ==================== CRUD Operations ====================

    async def create_or_update(self, dto: ResourceIndexCreateDTO) -> ResourceIndexResponse:
        """Create or update a resource index record.

        Flow 1: Store raw_content from parser. Tokenization happens in Flow 2.
        """
        content_updated_at = datetime.now(UTC)

        record = await self._repo.upsert(
            tenant_id=dto.tenant_id,
            resource_type=dto.resource_type,
            resource_id=dto.resource_id,
            owner_id=dto.owner_id,
            raw_content=dto.raw_content,
            content_updated_at=content_updated_at,
            parent_id=dto.parent_id,
            source_parser=dto.source_parser,
        )
        logger.info(
            "Upserted resource index: tenant_id=%s, resource_type=%s, resource_id=%s",
            dto.tenant_id,
            dto.resource_type,
            dto.resource_id,
        )
        return domain_to_response(db_to_domain(record))

    async def get_by_resource(self, resource_type: SearchableResourceType, resource_id: int) -> ResourceIndexResponse:
        """Get resource index by type and ID."""
        record = await self._repo.get_by_resource(self.tenant_id, resource_type, resource_id)
        if not record:
            from apps.shared.core.exceptions import ResourceNotFoundError

            raise ResourceNotFoundError(f"Resource index not found: {resource_type}/{resource_id}")
        return domain_to_response(db_to_domain(record))

    async def delete(self, resource_type: SearchableResourceType, resource_id: int) -> bool:
        """Delete resource index record and its underlying vector store entries."""
        record = await self._repo.get_by_resource(self.tenant_id, resource_type, resource_id)
        if not record:
            return False

        try:
            removed_vectors = await self.rag_manager.remove_by_resource(record.resource_type, record.resource_id)
            if removed_vectors:
                logger.info(
                    "Removed vector entries for %s/%s (tenant_id=%s)",
                    resource_type,
                    resource_id,
                    self.tenant_id,
                )
        except Exception as exc:
            logger.warning(
                "Failed to remove vector store entries for resource index %d: %s",
                record.id,
                exc,
            )

        return await self._repo.delete_by_resource(self.tenant_id, resource_type, resource_id)

    # ==================== Status Operations ====================

    async def mark_all_vectors_stale(self) -> int:
        """Mark all vector records as stale for current tenant (embedding model change)."""
        count = await self._repo.mark_all_vectors_stale(self.tenant_id)
        logger.info("Marked %d resource index records as stale for tenant %d", count, self.tenant_id)
        return count

    async def cleanup_orphan_vectors(
        self, resource_type: SearchableResourceType, *, dry_run: bool = False
    ) -> dict[str, Any]:
        """Detect and clean up orphaned vectors for a given resource type.

        Compares resource_ids in the vector store against the resource_index table
        to find vectors that no longer have a corresponding DB record.

        Args:
            resource_type: Resource type to check (e.g., "document", "asset", "api_connector")
            dry_run: If True, only report orphans without deleting

        Returns:
            Dict with orphaned_count, cleaned_count, and orphaned_ids (limited to 20).
        """
        db_ids = await self._repo.get_resource_ids_by_type(self.tenant_id, resource_type)
        vector_ids = await self.rag_manager.get_resource_ids_by_type(resource_type)
        orphaned_ids = vector_ids - db_ids

        if not orphaned_ids:
            return {
                "resource_type": resource_type,
                "orphaned_count": 0,
                "cleaned_count": 0,
            }

        cleaned_count = 0
        if not dry_run:
            cleaned_count = await self.rag_manager.delete_by_resource_type(resource_type, orphaned_ids)

        return {
            "resource_type": resource_type,
            "orphaned_count": len(orphaned_ids),
            "cleaned_count": cleaned_count,
            "orphaned_ids": list(orphaned_ids)[:20],
        }

    async def list_pending_items(
        self, statuses: list[str] | None = None, limit: int = 50
    ) -> list[ResourceIndexPendingItem]:
        """List records needing vector indexing (for scheduler).

        Retry eligibility is controlled by vector_next_retry_at in the repository.
        """
        query_statuses = statuses or ["pending", "stale", "failed"]
        records = await self._repo.list_by_statuses(self.tenant_id, statuses=query_statuses, limit=limit)
        return [
            ResourceIndexPendingItem(
                id=r.id,
                tenant_id=r.tenant_id,
                resource_type=r.resource_type,
                resource_id=r.resource_id,
                raw_content=r.raw_content,
                vector_retry_count=r.vector_retry_count,
                owner_id=r.owner_id,
                parent_id=r.parent_id,
                source_parser=r.source_parser,
            )
            for r in records
        ]

    # ==================== Vector Sync Operations ====================

    # Exponential backoff delays in minutes: 0, 1, 5, 15, 60
    BACKOFF_DELAYS = [0, 1, 5, 15, 60]

    async def sync_all_pending(self, *, batch_size: int = 50) -> dict[str, Any]:
        """Sync all pending items in batches until complete.

        Fetches pending items in batches, processes each item, and repeats
        until no more pending items remain. Uses batch mode to control memory
        and provide clean recovery checkpoints.
        """
        total_synced = 0
        total_failed = 0
        all_errors: list[dict[str, Any]] = []
        batch_num = 0
        attempted_ids: set[int] = set()

        while True:
            batch_num += 1
            pending = await self.list_pending_items(limit=batch_size)
            pending_ids = {item.id for item in pending}
            if pending_ids and pending_ids <= attempted_ids:
                logger.warning(
                    "Vector sync retry loop detected for tenant %d; stopping after %d batch(es)",
                    self.tenant_id,
                    batch_num,
                )
                break
            attempted_ids.update(pending_ids)

            synced = 0
            failed = 0
            for item in pending:
                result = await self._sync_single_item(item)
                if result["success"]:
                    synced += 1
                else:
                    failed += 1
                    all_errors.append(result)

            total_synced += synced
            total_failed += failed
            logger.info("Batch %d completed: synced=%d, failed=%d", batch_num, synced, failed)
            if synced == 0 and failed == 0:
                break
            if batch_num > 1000:
                logger.warning("Max batch iterations reached for tenant %d", self.tenant_id)
                break

        logger.info(
            "Sync completed: tenant=%d, synced=%d, failed=%d, batches=%d",
            self.tenant_id,
            total_synced,
            total_failed,
            batch_num,
        )
        return {
            "status": "completed",
            "tenant_id": self.tenant_id,
            "total_synced": total_synced,
            "total_failed": total_failed,
            "batches_processed": batch_num,
            "error_details": all_errors[:50] if all_errors else None,
        }

    async def _sync_single_item(self, item: ResourceIndexPendingItem) -> dict[str, Any]:
        """Sync a single pending ResourceIndex record.

        Flow 2: Read raw_content → tokenize + chunk → save to FTS + Vector DB.
        """
        if not item.raw_content:
            error = "No raw_content in ResourceIndex"
            logger.warning("Sync skipped for resource index id=%d: %s", item.id, error)
            next_retry_at = self._calculate_next_retry_at(item.vector_retry_count)
            await self._repo.update_vector_failed(item.id, error, next_retry_at)
            return {"success": False, "id": item.id, "error": error}

        start_time = time.time()
        logger.debug("Syncing resource index: type=%s, resource_id=%d", item.resource_type, item.resource_id)

        try:
            # Delete existing chunks for this resource before adding new ones
            await self.rag_manager.remove_by_resource(item.resource_type, item.resource_id)
            logger.debug(
                "Deleted old chunks for resource: type=%s, resource_id=%d",
                item.resource_type,
                item.resource_id,
            )

            # Use ResourceParser to generate tokenized_content and chunks from raw_content
            blocks_document = None
            if item.raw_content and is_manifest_pointer(item.raw_content):
                if not self.file_storage:
                    raise ValueError("FileStorage required to load manifest blocks")
                storage_uri = get_storage_uri(item.raw_content)
                if not storage_uri:
                    raise ValueError("Manifest pointer missing storage_uri")
                blocks_document = await read_blocks_json(
                    self.file_storage,
                    storage_uri,
                    tenant_id=self.tenant_id,
                )

            parser = ResourceParser(file_storage=self.file_storage)
            parse_result = parser.from_raw(
                item.raw_content,
                item.resource_type,
                source_parser=item.source_parser or "default",
                blocks_document=blocks_document,
            )

            # Build payload with proper metadata
            base_meta = {
                META_RESOURCE_TYPE: item.resource_type,
                META_RESOURCE_ID: item.resource_id,
                META_TENANT_ID: self.tenant_id,
            }
            if item.owner_id is not None:
                base_meta[META_OWNER_ID] = item.owner_id
            if item.parent_id is not None:
                base_meta[META_PARENT_ID] = item.parent_id

            records = [
                IndexRecordPayload(
                    content=chunk.page_content,
                    metadata={
                        **(chunk.metadata or {}),
                        **base_meta,
                        META_CHUNK_INDEX: i,
                        META_TOTAL_CHUNKS: len(parse_result.chunks),
                    },
                )
                for i, chunk in enumerate(parse_result.chunks)
            ]
            payload = IndexUpsertPayload(records=records)
            await self._upsert_to_vectordb(payload)

            # Compute hash from raw_content JSON for change detection
            hash_source = item.raw_content or {}
            if blocks_document is not None:
                hash_source = {**hash_source, "content_hash": hash_source.get("content_hash")}
            content_hash = _compute_content_hash(json.dumps(hash_source, sort_keys=True))
            await self._repo.update_vector_synced(
                item.id,
                vector_content_hash=content_hash,
                tokenized_content=parse_result.tokenized_content,
            )

            elapsed = time.time() - start_time
            logger.debug(
                "Sync completed: type=%s, resource_id=%d, chunks=%d, time=%.2fs",
                item.resource_type,
                item.resource_id,
                len(parse_result.chunks),
                elapsed,
            )
            return {"success": True, "id": item.id}
        except Exception as exc:
            logger.warning("Sync failed for resource index id=%d: %s", item.id, exc, exc_info=True)
            next_retry_at = self._calculate_next_retry_at(item.vector_retry_count)
            await self._repo.update_vector_failed(item.id, str(exc), next_retry_at)
            return {"success": False, "id": item.id, "error": str(exc)}

    # ==================== Vector Sync Helpers ====================

    @classmethod
    def _calculate_next_retry_at(cls, retry_count: int) -> datetime | None:
        """Calculate next retry time based on exponential backoff.

        Args:
            retry_count: Current retry count (will be incremented by 1)

        Returns:
            datetime when retry is allowed, or None for immediate retry
        """
        new_retry_count = retry_count + 1
        backoff_minutes = cls.BACKOFF_DELAYS[min(new_retry_count, len(cls.BACKOFF_DELAYS) - 1)]
        if backoff_minutes == 0:
            return None
        return datetime.now(UTC) + timedelta(minutes=backoff_minutes)

    async def _get_document_model(self, doc_id: int) -> DocumentModel | None:
        stmt = select(DocumentModel).where(DocumentModel.id == doc_id, DocumentModel.tenant_id == self.tenant_id)
        result = await self.db_session.execute(stmt)
        return result.scalar_one_or_none()

    async def _upsert_to_vectordb(self, payload: IndexUpsertPayload) -> int:
        """Upsert payload to VectorDB via RAGManager."""
        return await self.rag_manager.add_chunks(
            [Document(page_content=r.content, metadata=r.metadata) for r in payload.records]
        )
