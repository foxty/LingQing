"""Shared document types and enums."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Literal, TypedDict


class DocumentStatus(StrEnum):
    PROCESSING = "processing"
    ACTIVE = "active"
    FAILED = "failed"
    DELETED = "deleted"


class DocumentProcessOutcome(StrEnum):
    """Result of one worker attempt to process a document."""

    SUBMITTED = "submitted"
    COMPLETED = "completed"


class PollJobOutcome(StrEnum):
    """Result of one worker attempt to poll an async parse job."""

    COMPLETED = "completed"
    FAILED = "failed"
    PENDING = "pending"
    SKIPPED = "skipped"


class ParseJobStatus(StrEnum):
    """Normalized async parser job status returned by poll()."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"

    @classmethod
    def is_in_progress(cls, status: str) -> bool:
        return status in {cls.PENDING, cls.PROCESSING}


BlockType = Literal["text", "heading", "table", "image", "mixed"]
IntakeSource = Literal["upload", "drive_sync"]

BLOCK_TYPE_TEXT = "text"
BLOCK_TYPE_HEADING = "heading"
BLOCK_TYPE_TABLE = "table"
BLOCK_TYPE_IMAGE = "image"


@dataclass(frozen=True)
class DocumentImageFile:
    content: bytes
    media_type: str


class BlockBBox(TypedDict):
    """Top-left box: y grows downward."""

    left: float
    top: float
    right: float
    bottom: float


class DocumentBlock(TypedDict, total=False):
    type: BlockType | str
    text: str
    page: int
    uri: str
    caption: str | None
    bbox: BlockBBox


class BlocksDocument(TypedDict):
    schema_version: int
    parser: str
    blocks: list[DocumentBlock]


class ManifestMeta(TypedDict):
    filename: str
    parser: str


class ManifestPointer(TypedDict):
    schema_version: int
    storage_uri: str
    content_hash: str
    block_summary: dict[str, int]
    meta: ManifestMeta


class ProcessPendingResult(TypedDict):
    processed: int
    completed: int
    submitted: int
    failed: int


class PollPendingResult(TypedDict):
    completed: int
    failed: int
    polled: int


class DocumentParseWorkerResult(TypedDict):
    queued: int
    completed: int
    submitted: int
    failed: int
    polled: int


class DocumentStatusCount(TypedDict):
    tenant_id: int
    status: str
    count: int


class ParseIndexStatus(TypedDict):
    tenant_id: int
    total: int
    parsed: int
    async_pending: int
    parse_errors: int
    last_parsed_at: datetime | None


class VectorIndexStatusCount(TypedDict):
    tenant_id: int
    vector_status: str
    count: int


class ParseStatusSnapshot(TypedDict):
    documents: list[DocumentStatusCount]
    parse_index: list[ParseIndexStatus]
    vector_index: list[VectorIndexStatusCount]


class ParseIssueRow(TypedDict):
    document_id: int
    filename: str
    status: str
    parse_job_id: str | None
    parsed_at: datetime | None
    parse_error: str | None
    vector_status: str


def document_status_value(status: DocumentStatus | str | None) -> str | None:
    if status is None:
        return None
    if isinstance(status, DocumentStatus):
        return status.value
    return status


def coerce_document_status(status: str | None) -> DocumentStatus | None:
    if status is None:
        return None
    return DocumentStatus(status)
