"""Domain models for document module."""

from dataclasses import dataclass
from datetime import UTC, datetime

from apps.shared.document.types import DocumentStatus, IntakeSource
from apps.shared.domain.base_domain_model import BaseDomainModel


@dataclass
class DocumentDomain(BaseDomainModel):
    """Document domain model for knowledge base."""

    id: int
    tenant_id: int
    collection_id: int
    filename: str
    file_url: str  # Tenant-relative storage key or cloud URI (s3://...)
    file_size: int
    file_hash: str | None
    status: DocumentStatus | None
    owner_id: int | None
    upload_date: datetime
    created_at: datetime
    updated_at: datetime
    owner_username: str | None = None
    # Vector index status fields from ResourceIndex
    vector_status: str | None = None
    vector_synced_at: datetime | None = None
    vector_sync_error: str | None = None
    vector_sync_error_at: datetime | None = None
    source_parser: str | None = None
    parsed_at: datetime | None = None
    parse_error: str | None = None
    intake_source: IntakeSource = "upload"

    def is_ready(self) -> bool:
        return self.status == DocumentStatus.ACTIVE

    def is_processing(self) -> bool:
        return self.status == DocumentStatus.PROCESSING

    def has_failed(self) -> bool:
        return self.status == DocumentStatus.FAILED

    def is_supported_file_type(self) -> bool:
        """Check if document file type is supported for processing.

        Returns:
            True if the file extension is supported.
        """
        import os

        from apps.config import AppConfig

        ext = os.path.splitext(self.filename)[1].lower()
        return ext in AppConfig.SUPPORTED_DOCUMENT_EXTENSIONS

    @staticmethod
    def create_new(
        tenant_id: int,
        collection_id: int,
        filename: str,
        file_url: str,
        file_size: int,
        file_hash: str,
        owner_id: int,
    ) -> "DocumentDomain":
        return DocumentDomain(
            id=0,  # Placeholder, to be set by DB
            tenant_id=tenant_id,
            collection_id=collection_id,
            filename=filename,
            file_url=file_url,
            file_size=file_size,
            file_hash=file_hash,
            status=DocumentStatus.PROCESSING,
            owner_id=owner_id,
            upload_date=datetime.now(UTC),
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )


@dataclass
class DocumentCollectionDomain(BaseDomainModel):
    """Document collection aggregate root."""

    id: int
    tenant_id: int
    name: str
    description: str | None
    owner_id: int
    created_at: datetime
    updated_at: datetime
    owner_name: str | None = None
    document_count: int = 0

    @staticmethod
    def create_new(
        *,
        tenant_id: int,
        name: str,
        description: str | None,
        owner_id: int,
    ) -> "DocumentCollectionDomain":
        now = datetime.now(UTC)
        return DocumentCollectionDomain(
            id=0,
            tenant_id=tenant_id,
            name=name.strip(),
            description=description.strip() if description else None,
            owner_id=owner_id,
            created_at=now,
            updated_at=now,
        )
