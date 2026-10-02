"""DTOs for document module."""

from pydantic import BaseModel, Field

from apps.shared.document.types import BlockType, DocumentStatus, IntakeSource


class DocumentInfo(BaseModel):
    """Document information model."""

    id: int  # Database integer ID
    collection_id: int
    filename: str
    file_url: str
    upload_date: str
    file_size: int
    tenant_id: int  # Database integer ID
    status: DocumentStatus = DocumentStatus.ACTIVE
    file_hash: str | None = None  # SHA256 hash for deduplication
    owner_username: str | None = None  # Canonical owner username
    updated_at: str | None = None  # Last update timestamp
    # Vector index status fields from ResourceIndex
    vector_status: str | None = None
    last_vector_synced_at: str | None = None  # Last successful vector index timestamp
    last_vector_sync_error: str | None = None  # Last vector index error message
    source_parser: str | None = None
    parsed_at: str | None = None
    parse_error: str | None = None
    intake_source: IntakeSource = "upload"
    external_file_id: str | None = None


class DocumentParsedBlock(BaseModel):
    type: str
    text: str | None = None
    caption: str | None = None
    page: int | None = None
    uri: str | None = None


class DocumentQueueResponse(BaseModel):
    """Response for bulk document queue operations."""

    queued_count: int
    skipped_count: int = 0


class DocumentParsedContent(BaseModel):
    document_id: int
    filename: str
    parser: str | None = None
    parsed_at: str | None = None
    parse_error: str | None = None
    block_count: int
    truncated: bool = False
    type_counts: dict[str, int] = Field(default_factory=dict)
    blocks: list[DocumentParsedBlock] = Field(default_factory=list)


class DocumentChunk(BaseModel):
    """Document content chunk."""

    chunk_index: int
    content: str
    relevance: float | None = None
    page: int | None = None
    block_type: BlockType | None = None
    image_uri: str | None = None


class DocumentSearchResult(BaseModel):
    """Document search result with metadata and content chunks."""

    doc_id: int
    collection_id: int
    filename: str
    rrf_score: float | None = None
    source: str | None = None  # fts, vector, or hybrid
    highlight: str | None = None  # FTS highlighted preview
    chunks: list[DocumentChunk] = []


class DocumentCollectionCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)


class DocumentCollectionUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)


class DocumentCollectionResponse(BaseModel):
    id: int
    tenant_id: int
    name: str
    description: str | None = None
    owner_id: int
    owner_name: str | None = None
    document_count: int = 0
    can_write: bool = False
    can_manage: bool = False
    has_drive_sync: bool = False
    sync_folder_name: str | None = None
    sync_status: str | None = None
    last_synced_at: str | None = None
    created_at: str
    updated_at: str
