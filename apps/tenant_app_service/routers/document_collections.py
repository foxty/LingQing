"""Document collections router."""

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.config import get_file_storage
from apps.shared.authz.ta_permissions import TenantAppPermissions as Permissions
from apps.shared.core.auth import require_permission
from apps.shared.core.transaction import transaction
from apps.shared.db.session import get_db
from apps.shared.document.collection_service import DocumentCollectionService
from apps.shared.document.schemas import (
    DocumentCollectionCreate,
    DocumentCollectionResponse,
    DocumentCollectionUpdate,
    DocumentQueueResponse,
)
from apps.shared.document.service import DocumentService
from apps.shared.domain.actor import ActorContext
from apps.shared.domain.types import ABAC_ACTION_READ, ABAC_ACTION_WRITE, RESOURCE_TYPE_DOCUMENT_COLLECTION
from apps.shared.infra.storage import FileStorage
from apps.shared.schemas.user import UserDTO
from apps.shared.tag.adapters import domain_tag_value_to_api
from apps.shared.tag.schemas import TagBindingCreateRequest, TagValueDTO
from apps.shared.tag.service import TagService

router = APIRouter(prefix="/document-collections", tags=["document-collections"])


def _create_service(db: AsyncSession, tenant_id: int) -> DocumentCollectionService:
    return DocumentCollectionService(tenant_id=tenant_id, db_session=db)


def _create_document_service(
    db: AsyncSession,
    tenant_id: int,
    file_storage: FileStorage,
) -> DocumentService:
    return DocumentService(tenant_id=tenant_id, db_session=db, file_storage=file_storage)


def get_file_storage_dependency() -> FileStorage:
    return get_file_storage()


def _create_tag_service(db: AsyncSession, tenant_id: int) -> TagService:
    return TagService.create(tenant_id, db)


def _actor_from_user(current_user: UserDTO) -> ActorContext:
    return ActorContext(
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        user_role=current_user.role,
    )


@router.get("", response_model=list[DocumentCollectionResponse])
async def list_document_collections(
    current_user: UserDTO = Depends(require_permission(Permissions.DOCUMENTS_READ)),
    db: AsyncSession = Depends(get_db),
):
    service = _create_service(db, current_user.tenant_id)
    return await service.list_collections_for_actor(actor=_actor_from_user(current_user))


@router.post("", response_model=DocumentCollectionResponse, status_code=status.HTTP_201_CREATED)
@transaction
async def create_document_collection(
    payload: DocumentCollectionCreate,
    current_user: UserDTO = Depends(require_permission(Permissions.DOCUMENTS_WRITE)),
    db: AsyncSession = Depends(get_db),
):
    service = _create_service(db, current_user.tenant_id)
    return await service.create_collection(payload=payload, actor=_actor_from_user(current_user))


@router.get("/{collection_id}", response_model=DocumentCollectionResponse)
async def get_document_collection(
    collection_id: int,
    current_user: UserDTO = Depends(require_permission(Permissions.DOCUMENTS_READ)),
    db: AsyncSession = Depends(get_db),
):
    service = _create_service(db, current_user.tenant_id)
    return await service.get_collection_for_actor(
        collection_id=collection_id,
        actor=_actor_from_user(current_user),
    )


@router.put("/{collection_id}", response_model=DocumentCollectionResponse)
@transaction
async def update_document_collection(
    collection_id: int,
    payload: DocumentCollectionUpdate,
    current_user: UserDTO = Depends(require_permission(Permissions.DOCUMENTS_WRITE)),
    db: AsyncSession = Depends(get_db),
):
    service = _create_service(db, current_user.tenant_id)
    return await service.update_collection(
        collection_id=collection_id,
        payload=payload,
        actor=_actor_from_user(current_user),
    )


@router.post("/{collection_id}/reparse", response_model=DocumentQueueResponse)
@transaction
async def queue_collection_reparse(
    collection_id: int,
    current_user: UserDTO = Depends(require_permission(Permissions.DOCUMENTS_WRITE)),
    db: AsyncSession = Depends(get_db),
    file_storage: FileStorage = Depends(get_file_storage_dependency),
):
    """Queue all documents in a collection for background re-parsing."""
    document_service = _create_document_service(db, current_user.tenant_id, file_storage)
    return await document_service.queue_collection_reparse(
        collection_id,
        requester_id=current_user.id,
        requester_role=current_user.role,
        triggered_by="api",
    )


@router.post("/{collection_id}/reindex", response_model=DocumentQueueResponse)
@transaction
async def queue_collection_reindex(
    collection_id: int,
    current_user: UserDTO = Depends(require_permission(Permissions.DOCUMENTS_WRITE)),
    db: AsyncSession = Depends(get_db),
    file_storage: FileStorage = Depends(get_file_storage_dependency),
):
    """Queue all parsed documents in a collection for background vector re-indexing."""
    document_service = _create_document_service(db, current_user.tenant_id, file_storage)
    return await document_service.queue_collection_reindex(
        collection_id,
        requester_id=current_user.id,
        requester_role=current_user.role,
    )


@router.delete("/{collection_id}", status_code=status.HTTP_204_NO_CONTENT)
@transaction
async def delete_document_collection(
    collection_id: int,
    current_user: UserDTO = Depends(require_permission(Permissions.DOCUMENTS_WRITE)),
    db: AsyncSession = Depends(get_db),
):
    service = _create_service(db, current_user.tenant_id)
    await service.delete_collection(collection_id=collection_id, actor=_actor_from_user(current_user))


@router.get("/{collection_id}/tags", response_model=list[TagValueDTO], include_in_schema=False)
async def list_collection_tags(
    collection_id: int,
    current_user: UserDTO = Depends(require_permission(Permissions.DOCUMENTS_READ)),
    db: AsyncSession = Depends(get_db),
):
    service = _create_service(db, current_user.tenant_id)
    await service.require_collection_access(
        collection_id=collection_id,
        actor=_actor_from_user(current_user),
        action=ABAC_ACTION_READ,
    )
    tag_service = _create_tag_service(db, current_user.tenant_id)
    tag_values = await tag_service.list_tags_for_resource(RESOURCE_TYPE_DOCUMENT_COLLECTION, collection_id)
    return [domain_tag_value_to_api(tag_value) for tag_value in tag_values]


@router.post("/{collection_id}/tags", response_model=TagValueDTO, include_in_schema=False)
async def bind_collection_tag(
    collection_id: int,
    payload: TagBindingCreateRequest,
    current_user: UserDTO = Depends(require_permission(Permissions.TAGS_MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    service = _create_service(db, current_user.tenant_id)
    await service.require_collection_access(
        collection_id=collection_id,
        actor=_actor_from_user(current_user),
        action=ABAC_ACTION_WRITE,
    )
    tag_service = _create_tag_service(db, current_user.tenant_id)
    tag_value = await tag_service.bind_tag_value(
        resource_type=RESOURCE_TYPE_DOCUMENT_COLLECTION,
        resource_id=collection_id,
        tag_value_id=payload.tag_value_id,
        created_by=current_user.id,
    )
    return domain_tag_value_to_api(tag_value)


@router.delete("/{collection_id}/tags/{tag_value_id}", status_code=204, include_in_schema=False)
async def unbind_collection_tag(
    collection_id: int,
    tag_value_id: int,
    current_user: UserDTO = Depends(require_permission(Permissions.TAGS_MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    service = _create_service(db, current_user.tenant_id)
    await service.require_collection_access(
        collection_id=collection_id,
        actor=_actor_from_user(current_user),
        action=ABAC_ACTION_WRITE,
    )
    tag_service = _create_tag_service(db, current_user.tenant_id)
    await tag_service.unbind_tag_value(
        resource_type=RESOURCE_TYPE_DOCUMENT_COLLECTION,
        resource_id=collection_id,
        tag_value_id=tag_value_id,
    )
