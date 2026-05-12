"""Adapters for ResourceIndex model conversions.

Follows the project pattern: DB ↔ Domain ↔ Response conversions.
"""

from __future__ import annotations

from datetime import UTC, datetime

from apps.shared.db.models import ResourceIndex
from apps.shared.search.domain import ResourceIndexDomain, VectorStatus
from apps.shared.search.schemas import ResourceIndexResponse


def db_to_domain(db_model: ResourceIndex) -> ResourceIndexDomain:
    """Convert DB model to domain model."""
    raw_status = db_model.vector_status or "pending"
    try:
        vector_status = VectorStatus(raw_status)
    except ValueError:
        vector_status = VectorStatus.PENDING

    return ResourceIndexDomain(
        id=db_model.id,
        tenant_id=db_model.tenant_id,
        resource_type=db_model.resource_type,
        resource_id=db_model.resource_id,
        raw_content=db_model.raw_content,
        vector_status=vector_status,
        vector_content_hash=db_model.vector_content_hash,
        vector_synced_at=db_model.vector_synced_at,
        vector_sync_error_at=db_model.vector_sync_error_at,
        vector_sync_error=db_model.vector_sync_error,
        vector_retry_count=db_model.vector_retry_count,
        content_updated_at=db_model.content_updated_at,
        created_at=db_model.created_at,
        updated_at=db_model.updated_at,
    )


def domain_to_response(domain: ResourceIndexDomain) -> ResourceIndexResponse:
    """Convert domain model to response DTO."""
    return ResourceIndexResponse(
        id=domain.id,
        tenant_id=domain.tenant_id,
        resource_type=domain.resource_type,
        resource_id=domain.resource_id,
        raw_content=domain.raw_content,
        vector_status=domain.vector_status,
        vector_content_hash=domain.vector_content_hash,
        vector_synced_at=domain.vector_synced_at,
        vector_sync_error_at=domain.vector_sync_error_at,
        vector_sync_error=domain.vector_sync_error,
        vector_retry_count=domain.vector_retry_count,
        content_updated_at=domain.content_updated_at,
        created_at=domain.created_at or datetime.now(UTC),
        updated_at=domain.updated_at or datetime.now(UTC),
    )
