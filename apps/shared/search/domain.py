"""Search domain models — pure business logic, zero framework dependencies."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from apps.shared.domain.types import (
    RESOURCE_TYPE_API_CONNECTOR,
    RESOURCE_TYPE_ASSET,
    RESOURCE_TYPE_DOCUMENT,
)

# Resource type constants for use in domain logic
RESOURCE_TYPES = (RESOURCE_TYPE_DOCUMENT, RESOURCE_TYPE_ASSET, RESOURCE_TYPE_API_CONNECTOR)


class VectorStatus(StrEnum):
    """Lifecycle states for vector index synchronization.

    State transitions:
        pending → indexing → indexed
        indexed → stale → indexing → indexed
        pending/stale/failed → indexing → failed → (retry) → pending
        failed → permanent_failed (after max retries)
    """

    PENDING = "pending"  #: Newly created, awaiting vector indexing
    INDEXING = "indexing"  #: Currently being processed (prevents concurrent sync)
    INDEXED = "indexed"  #: Successfully synced to vector store
    STALE = "stale"  #: Content changed, needs re-indexing
    FAILED = "failed"  #: Sync failed, eligible for retry
    PERMANENT_FAILED = "permanent_failed"  #: Max retries exceeded, no more automatic retries


@dataclass
class ResourceIndexDomain:
    """Domain model representing a resource index record.

    This model tracks the synchronization state between application resources
    (documents, assets, API operations) and the search/vector index layer.

    Key fields:
        resource_type: Type identifier (e.g., "document", "asset", "api_connector")
        resource_id: Internal DB primary key of the source resource
        raw_content: Structured content from parser for FTS and vector indexing
        vector_status: Current vector sync lifecycle state (see VectorStatus)
        vector_content_hash: SHA256 hash of indexed content for change detection
        content_updated_at: Timestamp of last content change (drives sync ordering)

    Business rules:
        - vector_status transitions are managed by the repository sync methods
        - content_updated_at is used to order sync jobs (oldest first)
        - vector_content_hash enables efficient change detection without re-indexing
        - vector_retry_count increments on failure, blocks after max_retries
    """

    id: int
    tenant_id: int
    resource_type: str  #: One of RESOURCE_TYPE_DOCUMENT, RESOURCE_TYPE_ASSET, RESOURCE_TYPE_API_CONNECTOR
    resource_id: int
    raw_content: dict | None = None  #: Structured content from parser for FTS and vector indexing
    vector_status: VectorStatus = VectorStatus.PENDING
    vector_content_hash: str | None = None
    vector_synced_at: datetime | None = None
    vector_sync_error_at: datetime | None = None
    vector_sync_error: str | None = None
    vector_retry_count: int = 0
    vector_next_retry_at: datetime | None = None
    content_updated_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
