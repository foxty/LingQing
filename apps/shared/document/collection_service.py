"""Document collection application service."""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from apps.shared.authz.authz_query_builder import (
    AuthzSqlFilter,
    build_unified_resource_filter,
)
from apps.shared.authz.delegation import allows_delegated_read
from apps.shared.authz.ta_permissions import TenantAppPermissions
from apps.shared.authz.ta_rbac import role_has_permission
from apps.shared.core.base_service import TenantAwareService
from apps.shared.core.exceptions import (
    AuthorizationError,
    DuplicateResourceError,
    ResourceNotFoundError,
    ValidationError,
)
from apps.shared.db.models import Document, DocumentCollection, ResourceIndex
from apps.shared.document.adapters import db_collection_to_domain, domain_collection_to_api
from apps.shared.document.domain import DocumentCollectionDomain
from apps.shared.document.repository import DocumentCollectionRepository
from apps.shared.document.schemas import DocumentCollectionCreate, DocumentCollectionResponse, DocumentCollectionUpdate
from apps.shared.document.sync_repository import DocumentSyncRepository
from apps.shared.domain.actor import ActorContext
from apps.shared.domain.types import (
    ABAC_ACTION_READ,
    ABAC_ACTION_WRITE,
    AUTHZ_ACTION_MANAGE,
    RESOURCE_TYPE_DOCUMENT_COLLECTION,
    AbacAction,
)
from apps.shared.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class DocumentAccessScope:
    deny_all: bool
    allow_all: bool
    document_filter: ColumnElement[bool] | None
    index_parent_filter: ColumnElement[bool] | None


class DocumentCollectionService(TenantAwareService):
    def __init__(self, tenant_id: int, db_session: AsyncSession):
        super().__init__(tenant_id, db_session=db_session)
        self._repo = DocumentCollectionRepository(db_session)

    async def has_collections_manage_permission(self, *, actor: ActorContext) -> bool:
        return await role_has_permission(
            db=self.db_session,
            tenant_id=actor.tenant_id,
            role_key=actor.user_role,
            permission=TenantAppPermissions.DOCUMENTS_MANAGE,
        )

    async def _build_collection_auth_scope(
        self,
        *,
        actor: ActorContext,
        action: AbacAction,
    ) -> AuthzSqlFilter:
        has_manage = await self.has_collections_manage_permission(actor=actor)
        return await build_unified_resource_filter(
            db_session=self.db_session,
            tenant_id=self.tenant_id,
            user_id=actor.user_id,
            user_role=actor.user_role,
            resource_type=RESOURCE_TYPE_DOCUMENT_COLLECTION,
            action=action,
            resource_model=DocumentCollection,
            has_manage_permission=has_manage,
        )

    async def build_document_access_scope(self, *, actor: ActorContext, action: AbacAction) -> DocumentAccessScope:
        """Resolve which documents are visible based on collection-level authz."""
        scope = await self._build_collection_auth_scope(actor=actor, action=action)
        if scope.deny_all:
            return DocumentAccessScope(
                deny_all=True,
                allow_all=False,
                document_filter=None,
                index_parent_filter=None,
            )
        if scope.allow_all:
            return DocumentAccessScope(
                deny_all=False,
                allow_all=True,
                document_filter=None,
                index_parent_filter=None,
            )

        allowed_collections = (
            select(DocumentCollection.id)
            .where(
                DocumentCollection.tenant_id == self.tenant_id,
                scope.clause,
            )
            .scalar_subquery()
        )
        document_filter = Document.collection_id.in_(allowed_collections)
        index_parent_filter = ResourceIndex.parent_id.in_(allowed_collections)
        return DocumentAccessScope(
            deny_all=False,
            allow_all=False,
            document_filter=document_filter,
            index_parent_filter=index_parent_filter,
        )

    async def require_document_access(
        self,
        *,
        document_id: int,
        actor: ActorContext,
        action: AbacAction,
        delegated_ids: list[int] | None = None,
    ) -> int:
        """Ensure the actor can access a document via its collection."""
        stmt = select(Document.collection_id).where(
            Document.tenant_id == self.tenant_id,
            Document.id == document_id,
        )
        collection_id = await self.db_session.scalar(stmt)
        if collection_id is None:
            raise ResourceNotFoundError(f"Document {document_id} not found")
        await self.require_collection_access(
            collection_id=collection_id,
            actor=actor,
            action=action,
            delegated_ids=delegated_ids,
        )
        return collection_id

    async def require_collection_access(
        self,
        *,
        collection_id: int,
        actor: ActorContext,
        action: AbacAction,
        delegated_ids: list[int] | None = None,
    ) -> DocumentCollectionDomain:
        collection = await self._get_domain(collection_id)
        if collection is None:
            raise ResourceNotFoundError(f"Document collection {collection_id} not found")

        has_manage = await self.has_collections_manage_permission(actor=actor)
        allowed = await allows_delegated_read(
            db_session=self.db_session,
            tenant_id=self.tenant_id,
            user_id=actor.user_id,
            user_role=actor.user_role,
            resource_type=RESOURCE_TYPE_DOCUMENT_COLLECTION,
            resource_id=collection.id,
            resource_owner_id=collection.owner_id,
            action=action,
            has_manage_permission=has_manage,
            delegated_ids=delegated_ids,
        )
        if not allowed:
            raise AuthorizationError("无权访问该文档集合")
        return collection

    async def _collection_capabilities(
        self,
        collection: DocumentCollectionDomain,
        actor: ActorContext,
    ) -> tuple[bool, bool]:
        has_manage = await self.has_collections_manage_permission(actor=actor)
        can_write = await allows_delegated_read(
            db_session=self.db_session,
            tenant_id=self.tenant_id,
            user_id=actor.user_id,
            user_role=actor.user_role,
            resource_type=RESOURCE_TYPE_DOCUMENT_COLLECTION,
            resource_id=collection.id,
            resource_owner_id=collection.owner_id,
            action=ABAC_ACTION_WRITE,
            has_manage_permission=has_manage,
        )
        can_manage = await allows_delegated_read(
            db_session=self.db_session,
            tenant_id=self.tenant_id,
            user_id=actor.user_id,
            user_role=actor.user_role,
            resource_type=RESOURCE_TYPE_DOCUMENT_COLLECTION,
            resource_id=collection.id,
            resource_owner_id=collection.owner_id,
            action=AUTHZ_ACTION_MANAGE,
            has_manage_permission=has_manage,
        )
        return can_write, can_manage

    async def list_collections_for_actor(self, *, actor: ActorContext) -> list[DocumentCollectionResponse]:
        scope = await self._build_collection_auth_scope(actor=actor, action=ABAC_ACTION_READ)
        if scope.deny_all:
            return []

        collections = await self._repo.list_by_tenant(
            self.tenant_id,
            scope_clause=None if scope.allow_all else scope.clause,
        )
        collection_ids = [c.id for c in collections]
        counts = await self._repo.count_documents_by_collection(self.tenant_id, collection_ids)
        connectors = await DocumentSyncRepository(self.db_session).map_connectors_by_collection(
            self.tenant_id,
            collection_ids,
        )
        responses: list[DocumentCollectionResponse] = []
        for c in collections:
            domain = db_collection_to_domain(c, document_count=counts.get(c.id, 0))
            can_write, can_manage = await self._collection_capabilities(domain, actor)
            connector = connectors.get(c.id)
            responses.append(
                domain_collection_to_api(
                    domain,
                    can_write=can_write,
                    can_manage=can_manage,
                    has_drive_sync=connector is not None,
                    sync_folder_name=connector.source_folder_name if connector else None,
                    sync_status=connector.status if connector else None,
                    last_synced_at=connector.last_synced_at.isoformat() if connector and connector.last_synced_at else None,
                ),
            )
        return responses

    async def get_collection_for_actor(self, *, collection_id: int, actor: ActorContext) -> DocumentCollectionResponse:
        collection = await self.require_collection_access(
            collection_id=collection_id,
            actor=actor,
            action=ABAC_ACTION_READ,
        )
        can_write, can_manage = await self._collection_capabilities(collection, actor)
        connector = await DocumentSyncRepository(self.db_session).get_connector_by_collection(
            self.tenant_id,
            collection_id,
        )
        return domain_collection_to_api(
            collection,
            can_write=can_write,
            can_manage=can_manage,
            has_drive_sync=connector is not None,
            sync_folder_name=connector.source_folder_name if connector else None,
            sync_status=connector.status if connector else None,
            last_synced_at=connector.last_synced_at.isoformat() if connector and connector.last_synced_at else None,
        )

    async def create_collection(
        self,
        *,
        payload: DocumentCollectionCreate,
        actor: ActorContext,
    ) -> DocumentCollectionResponse:
        existing = await self._repo.get_by_tenant_and_name(self.tenant_id, payload.name.strip())
        if existing:
            raise DuplicateResourceError(f"Collection '{payload.name}' already exists")

        domain = DocumentCollectionDomain.create_new(
            tenant_id=self.tenant_id,
            name=payload.name,
            description=payload.description,
            owner_id=actor.user_id,
        )
        record = await self._repo.create(domain)
        logger.info("Created document collection id=%s tenant=%s", record.id, self.tenant_id)
        return domain_collection_to_api(db_collection_to_domain(record))

    async def update_collection(
        self,
        *,
        collection_id: int,
        payload: DocumentCollectionUpdate,
        actor: ActorContext,
    ) -> DocumentCollectionResponse:
        await self.require_collection_access(
            collection_id=collection_id,
            actor=actor,
            action=ABAC_ACTION_WRITE,
        )

        if payload.name:
            existing = await self._repo.get_by_tenant_and_name(self.tenant_id, payload.name.strip())
            if existing and existing.id != collection_id:
                raise DuplicateResourceError(f"Collection '{payload.name}' already exists")

        record = await self._repo.update_fields(
            collection_id,
            self.tenant_id,
            name=payload.name.strip() if payload.name else None,
            description=payload.description,
        )
        if record is None:
            raise ResourceNotFoundError(f"Document collection {collection_id} not found")

        count = await self._repo.count_documents_in_collection(collection_id, self.tenant_id)
        return domain_collection_to_api(db_collection_to_domain(record, document_count=count))

    async def delete_collection(self, *, collection_id: int, actor: ActorContext) -> None:
        await self.require_collection_access(
            collection_id=collection_id,
            actor=actor,
            action=ABAC_ACTION_WRITE,
        )
        doc_count = await self._repo.count_documents_in_collection(collection_id, self.tenant_id)
        if doc_count > 0:
            raise ValidationError("Collection is not empty; delete or move documents first")

        deleted = await self._repo.delete(collection_id, self.tenant_id)
        if not deleted:
            raise ResourceNotFoundError(f"Document collection {collection_id} not found")

    async def _get_domain(self, collection_id: int) -> DocumentCollectionDomain | None:
        record = await self._repo.get_by_id_and_tenant(collection_id, self.tenant_id)
        if record is None:
            return None
        count = await self._repo.count_documents_in_collection(collection_id, self.tenant_id)
        return db_collection_to_domain(record, document_count=count)
