"""Adapters for Document domain model conversions."""

from apps.shared.db import models as db_models
from apps.shared.document.domain import DocumentCollectionDomain, DocumentDomain
from apps.shared.document.schemas import DocumentCollectionResponse, DocumentInfo
from apps.shared.document.types import DocumentStatus, coerce_document_status, document_status_value

# ============ DB Conversions ============


def db_document_to_domain(
    db_doc: db_models.Document,
    resource_index: db_models.ResourceIndex | None = None,
) -> DocumentDomain:
    """Convert DB Document to Domain Document.

    Args:
        db_doc: Document DB model
        resource_index: Optional ResourceIndex for sync status
    """
    # Read directly from __dict__ so we don't trigger lazy loading in async contexts.
    owner_user = db_doc.__dict__.get("owner_user")
    owner_username: str | None = owner_user.username if owner_user else None

    return DocumentDomain(
        id=db_doc.id,
        tenant_id=db_doc.tenant_id,
        collection_id=db_doc.collection_id,
        filename=db_doc.filename,
        file_url=db_doc.file_url,
        file_size=db_doc.file_size,
        file_hash=db_doc.file_hash,
        status=coerce_document_status(db_doc.status),
        owner_id=db_doc.owner_id,
        owner_username=owner_username,
        upload_date=db_doc.upload_date,
        created_at=db_doc.created_at,
        updated_at=db_doc.updated_at,
        vector_status=resource_index.vector_status if resource_index else None,
        vector_synced_at=resource_index.vector_synced_at if resource_index else None,
        vector_sync_error=resource_index.vector_sync_error if resource_index else None,
        vector_sync_error_at=resource_index.vector_sync_error_at if resource_index else None,
        source_parser=resource_index.source_parser if resource_index else None,
        parsed_at=resource_index.parsed_at if resource_index else None,
        parse_error=resource_index.parse_error if resource_index else None,
    )


def domain_document_to_db_model(domain_doc: DocumentDomain) -> db_models.Document:
    """Convert Domain Document to dict for DB operations."""
    return db_models.Document(
        tenant_id=domain_doc.tenant_id,
        collection_id=domain_doc.collection_id,
        filename=domain_doc.filename,
        file_url=domain_doc.file_url,
        file_size=domain_doc.file_size,
        file_hash=domain_doc.file_hash,
        status=document_status_value(domain_doc.status) or DocumentStatus.PROCESSING.value,
        owner_id=domain_doc.owner_id,
        upload_date=domain_doc.upload_date,
    )


# ============ API Conversions ============


def domain_document_to_api(domain_doc: DocumentDomain) -> DocumentInfo:
    """Convert Domain Document to API DocumentInfo."""
    return DocumentInfo(
        id=domain_doc.id,
        collection_id=domain_doc.collection_id,
        filename=domain_doc.filename,
        file_url=domain_doc.file_url,
        upload_date=domain_doc.upload_date.isoformat(),
        file_size=domain_doc.file_size,
        tenant_id=domain_doc.tenant_id,
        status=domain_doc.status or DocumentStatus.PROCESSING,
        file_hash=domain_doc.file_hash,
        owner_username=domain_doc.owner_username,
        updated_at=domain_doc.updated_at.isoformat() if domain_doc.updated_at else None,
        vector_status=domain_doc.vector_status,
        last_vector_synced_at=domain_doc.vector_synced_at.isoformat() if domain_doc.vector_synced_at else None,
        last_vector_sync_error=domain_doc.vector_sync_error,
        source_parser=domain_doc.source_parser,
        parsed_at=domain_doc.parsed_at.isoformat() if domain_doc.parsed_at else None,
        parse_error=domain_doc.parse_error,
    )


def db_collection_to_domain(
    db_collection: db_models.DocumentCollection,
    *,
    document_count: int = 0,
) -> DocumentCollectionDomain:
    owner_user = db_collection.__dict__.get("owner_user")
    owner_name = owner_user.username if owner_user else None
    return DocumentCollectionDomain(
        id=db_collection.id,
        tenant_id=db_collection.tenant_id,
        name=db_collection.name,
        description=db_collection.description,
        owner_id=db_collection.owner_id,
        owner_name=owner_name,
        document_count=document_count,
        created_at=db_collection.created_at,
        updated_at=db_collection.updated_at,
    )


def domain_collection_to_db_model(domain: DocumentCollectionDomain) -> db_models.DocumentCollection:
    return db_models.DocumentCollection(
        tenant_id=domain.tenant_id,
        name=domain.name,
        description=domain.description,
        owner_id=domain.owner_id,
    )


def domain_collection_to_api(domain: DocumentCollectionDomain) -> DocumentCollectionResponse:
    return DocumentCollectionResponse(
        id=domain.id,
        tenant_id=domain.tenant_id,
        name=domain.name,
        description=domain.description,
        owner_id=domain.owner_id,
        owner_name=domain.owner_name,
        document_count=domain.document_count,
        created_at=domain.created_at.isoformat(),
        updated_at=domain.updated_at.isoformat(),
    )
