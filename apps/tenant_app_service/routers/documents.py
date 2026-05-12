"""Documents router."""

import os

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from apps.config import AppConfig, get_file_storage
from apps.shared.authz.ta_permissions import TenantAppPermissions as Permissions
from apps.shared.core.auth import require_permission
from apps.shared.core.transaction import transaction
from apps.shared.db.session import get_db
from apps.shared.document.adapters import domain_document_to_api
from apps.shared.document.schemas import DocumentInfo, DocumentParsedContent
from apps.shared.document.service import DocumentService
from apps.shared.infra.storage import FileStorage
from apps.shared.schemas.pagination import PaginatedResponse
from apps.shared.schemas.user import UserDTO

router = APIRouter(prefix="/documents", tags=["documents"])


def get_file_storage_dependency() -> FileStorage:
    """Dependency to get file storage instance."""
    return get_file_storage()


def _create_document_service(db: AsyncSession, tenant_id: int, file_storage: FileStorage) -> DocumentService:
    """Create DocumentService with injected database session."""
    return DocumentService(
        tenant_id=tenant_id,
        db_session=db,
        file_storage=file_storage,
    )


@router.get("", response_model=PaginatedResponse[DocumentInfo])
async def list_documents(
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(10, ge=1, le=100, description="Items per page"),
    query: str | None = Query(None, min_length=1, description="Search query"),
    collection_id: int | None = Query(None, description="Filter by document collection ID"),
    current_user: UserDTO = Depends(require_permission(Permissions.DOCUMENTS_READ)),
    db: AsyncSession = Depends(get_db),
    file_storage: FileStorage = Depends(get_file_storage_dependency),
):
    """List documents for the current user's tenant with pagination."""
    document_service = _create_document_service(db, current_user.tenant_id, file_storage)

    documents, pagination = await document_service.list_documents(
        requester_id=current_user.id,
        requester_role=current_user.role,
        page=page,
        page_size=page_size,
        query=query,
        collection_id=collection_id,
    )

    return PaginatedResponse(
        items=documents,
        total=pagination.total,
        page=pagination.page,
        page_size=pagination.page_size,
        total_pages=pagination.total_pages,
    )


@router.post("/upload", response_model=DocumentInfo)
@transaction
async def upload_document(
    file: UploadFile = File(...),
    collection_id: int = Form(..., description="Target document collection ID"),
    current_user: UserDTO = Depends(require_permission(Permissions.DOCUMENTS_WRITE)),
    db: AsyncSession = Depends(get_db),
    file_storage: FileStorage = Depends(get_file_storage_dependency),
):
    """Upload a document to the knowledge base for the current user's tenant."""
    file_ext = os.path.splitext(file.filename)[1].lower()
    if file_ext not in AppConfig.SUPPORTED_DOCUMENT_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=(f"不支持的文件类型: {file_ext}。支持的类型: {AppConfig.SUPPORTED_DOCUMENT_EXTENSIONS}"),
        )

    document_service = _create_document_service(db, current_user.tenant_id, file_storage)
    domain_document = await document_service.upload_document(
        file=file,
        owner_id=current_user.id,
        requester_role=current_user.role,
        collection_id=collection_id,
    )
    return domain_document_to_api(domain_document)


@router.post("/{document_id}/reparse", response_model=DocumentInfo)
@transaction
async def queue_document_reparse(
    document_id: int,
    current_user: UserDTO = Depends(require_permission(Permissions.DOCUMENTS_WRITE)),
    db: AsyncSession = Depends(get_db),
    file_storage: FileStorage = Depends(get_file_storage_dependency),
):
    """Queue document for background re-parsing."""
    document_service = _create_document_service(db, current_user.tenant_id, file_storage)
    domain_document = await document_service.queue_document_reparse(document_id, triggered_by="api")
    return domain_document_to_api(domain_document)


@router.post("/{document_id}/reindex", response_model=DocumentInfo)
@transaction
async def queue_document_reindex(
    document_id: int,
    current_user: UserDTO = Depends(require_permission(Permissions.DOCUMENTS_WRITE)),
    db: AsyncSession = Depends(get_db),
    file_storage: FileStorage = Depends(get_file_storage_dependency),
):
    """Queue document for background vector re-indexing."""
    document_service = _create_document_service(db, current_user.tenant_id, file_storage)
    domain_document = await document_service.queue_document_reindex(document_id)
    return domain_document_to_api(domain_document)


@router.get("/{document_id}/images/{filename}")
async def get_document_image(
    document_id: int,
    filename: str,
    current_user: UserDTO = Depends(require_permission(Permissions.DOCUMENTS_READ)),
    db: AsyncSession = Depends(get_db),
    file_storage: FileStorage = Depends(get_file_storage_dependency),
):
    """Return one stored parse image for a document the caller can read."""
    document_service = _create_document_service(db, current_user.tenant_id, file_storage)
    image = await document_service.read_document_image(
        document_id,
        filename,
        requester_id=current_user.id,
        requester_role=current_user.role,
    )
    return Response(
        content=image.content, media_type=image.media_type, headers={"Cache-Control": "private, max-age=3600"}
    )


@router.get("/{document_id}/parsed", response_model=DocumentParsedContent)
async def get_parsed_document(
    document_id: int,
    current_user: UserDTO = Depends(require_permission(Permissions.DOCUMENTS_READ)),
    db: AsyncSession = Depends(get_db),
    file_storage: FileStorage = Depends(get_file_storage_dependency),
):
    """Return stored parse blocks for preview (capped)."""
    document_service = _create_document_service(db, current_user.tenant_id, file_storage)
    return await document_service.get_parsed_content(
        document_id,
        requester_id=current_user.id,
        requester_role=current_user.role,
    )


@router.delete("", include_in_schema=False)
@transaction
async def delete_documents(
    doc_ids: list[int] = Query(..., description="Document IDs to delete"),
    current_user: UserDTO = Depends(require_permission(Permissions.DOCUMENTS_WRITE)),
    db: AsyncSession = Depends(get_db),
    file_storage: FileStorage = Depends(get_file_storage_dependency),
):
    """Delete one or multiple documents from the knowledge base."""
    document_service = _create_document_service(db, current_user.tenant_id, file_storage)
    unique_doc_ids = list(dict.fromkeys(doc_ids))
    return await document_service.delete_documents(
        unique_doc_ids,
        requester_id=current_user.id,
        requester_role=current_user.role,
    )
