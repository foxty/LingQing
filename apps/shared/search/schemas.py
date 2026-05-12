"""Search module schemas — DTOs for API contracts and service boundaries.

Domain models live in `domain.py`. This file contains only Pydantic DTOs
and dataclasses used for request/response boundaries.
"""

from datetime import datetime
from typing import Any, NotRequired, TypedDict

from pydantic import BaseModel, Field

from apps.shared.domain.types import (
    SEARCH_TARGET_API_CONNECTOR,
    SEARCH_TARGET_ASSET,
    SEARCH_TARGET_BOTH,
    SEARCH_TARGET_DOCUMENT,
    IndexSourceType,
    SearchableResourceType,
)
from apps.shared.search.domain import VectorStatus

# ==================== SearchTarget constants ====================


class SearchTarget:
    """Search target type constants."""

    DOCUMENT = SEARCH_TARGET_DOCUMENT
    ASSET = SEARCH_TARGET_ASSET
    API_CONNECTOR = SEARCH_TARGET_API_CONNECTOR
    BOTH = SEARCH_TARGET_BOTH


# ==================== ResourceIndex DTOs ====================


class ResourceIndexCreateDTO(BaseModel):
    """DTO for creating or updating a resource index record.

    Flow 1: Parse resource → save raw_content to ResourceIndex.
    Tokenization and chunking happen in Flow 2 (sync job).
    """

    tenant_id: int
    resource_type: IndexSourceType
    resource_id: int
    owner_id: int
    raw_content: dict | None = None
    content_updated_at: datetime | None = None
    parent_id: int | None = None
    source_parser: str = "default"


class ResourceIndexUpdateDTO(BaseModel):
    """DTO for updating a resource index record.

    All fields are optional — only provided fields are updated.
    Used for administrative corrections (e.g., fixing vector_status after manual intervention).
    """

    raw_content: dict | None = None
    vector_status: VectorStatus | None = None
    vector_content_hash: str | None = None
    vector_synced_at: datetime | None = None
    vector_sync_error_at: datetime | None = None
    vector_sync_error: str | None = None
    vector_retry_count: int | None = None
    content_updated_at: datetime | None = None


class ResourceIndexResponse(BaseModel):
    """DTO for resource index response.

    Represents the full state of a resource index record, including
    raw content, vector sync status, and error history.
    """

    id: int
    tenant_id: int
    resource_type: IndexSourceType
    resource_id: int
    raw_content: dict | None = None
    vector_status: VectorStatus
    vector_content_hash: str | None = None
    vector_synced_at: datetime | None = None
    vector_sync_error_at: datetime | None = None
    vector_sync_error: str | None = None
    vector_retry_count: int
    content_updated_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class ResourceIndexPendingItem(BaseModel):
    """Lightweight DTO for pending/stale items fetched by scheduler.

    Contains only the fields needed for vector sync processing,
    avoiding loading full record state into memory.
    """

    id: int
    tenant_id: int
    resource_type: IndexSourceType
    resource_id: int
    raw_content: dict | None = None
    vector_retry_count: int
    owner_id: int | None = None
    parent_id: int | None = None
    source_parser: str = "default"


# ==================== Search DTOs ====================


class DocumentSearchChunkHint(TypedDict):
    collection_id: int
    chunk_index: int
    chunk_content: str
    section_hint: str
    relevance: float | None
    page: NotRequired[int]
    block_type: NotRequired[str]
    image_url: NotRequired[str]


class ResourceContextChunk(BaseModel):
    """Context chunk payload for a vector-indexed resource.

    Represents a single chunk of content retrieved from the vector store,
    with optional positioning metadata for context window expansion.
    """

    chunk_index: int | None = None
    total_chunks: int | None = None
    content: str
    block_type: str | None = None
    image_uri: str | None = Field(default=None, exclude=True)
    page: int | None = None
    image_url: str | None = None
    image_markdown: str | None = None


class ResourceChunksResponse(BaseModel):
    """Chunk response for any indexed resource.

    Returns a range of chunks around an anchor point for context-aware retrieval.
    """

    resource_type: IndexSourceType
    resource_id: int
    anchor_chunk_indexes: list[int]
    context_range: int
    chunks: list[ResourceContextChunk]


class SearchResultItem(BaseModel):
    """Unified search result item.

    Aggregates results from FTS and vector search into a single shape,
    with resource_type indicating the source domain for downstream retrieval.
    """

    resource_type: SearchableResourceType = Field(..., description="Result type: document, asset, or api_connector")
    resource_id: int | str = Field(..., description="Resource identifier for retrieve_resource_context")
    title: str
    score: float | None = None
    source: str | None = Field(default=None, description="fts, vector, or hybrid")
    snippet: str | None = None
    contents: list[dict[str, Any]] = Field(default_factory=list, description="Type-specific structured data")


class SearchResponse(BaseModel):
    """Search response containing ranked items."""

    items: list[SearchResultItem]
    total: int
    page: int
    page_size: int
    total_pages: int
    has_next: bool = False
    has_prev: bool = False


class ApiConnectorSearchResult(BaseModel):
    """Search hit for an API connector operation."""

    operation_uid: str
    connector_id: int
    connector_name: str | None = None
    method: str
    path_template: str
    operation_id: int = Field(..., description="ApiOperationIndex.id (internal DB primary key)")
    summary: str = ""
    description: str | None = None
    tags: list[str] = Field(default_factory=list)
    rrf_score: float | None = None
    source: str | None = Field(default=None, description="fts, vector, or hybrid")


class AssetSearchResult(BaseModel):
    """Asset search result with metadata and data source info."""

    asset_id: int
    data_source_id: int
    data_source_name: str
    data_source_type: str
    asset_name: str
    asset_type: str
    resolved_description: str | None = None
    columns: list[dict[str, Any]]
    row_count: int | None
    rrf_score: float | None = None
    source: str | None = None  # fts, vector, or hybrid
