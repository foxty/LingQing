"""Document management service."""

from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.core.base_service import TenantAwareService
from apps.shared.core.exceptions import (
    InternalServiceError,
    ResourceNotFoundError,
    ValidationError,
)
from apps.shared.document.adapters import db_document_to_domain, domain_document_to_api
from apps.shared.document.collection_service import DocumentCollectionService
from apps.shared.document.domain import DocumentDomain
from apps.shared.document.intake import DocumentIntake, IntakeRequest
from apps.shared.document.manifest import (
    document_image_relative_key,
    get_storage_uri,
    image_media_type,
    read_blocks_json,
    summarize_blocks,
)
from apps.shared.document.parse_pipeline import DocumentParsePipeline
from apps.shared.document.repository import DBDocumentRepository
from apps.shared.document.sync_repository import DocumentSyncRepository
from apps.shared.document.schemas import (
    DocumentInfo,
    DocumentParsedBlock,
    DocumentParsedContent,
    DocumentQueueResponse,
)
from apps.shared.document.types import DocumentImageFile
from apps.shared.domain.actor import ActorContext
from apps.shared.domain.types import ABAC_ACTION_READ, ABAC_ACTION_WRITE, RESOURCE_TYPE_DOCUMENT
from apps.shared.infra.storage import FileStorage
from apps.shared.infra.storage.paths import resolve_storage_ref
from apps.shared.search.indexing_service import ResourceIndexService
from apps.shared.search.repository import ResourceIndexRepository
from apps.shared.tenant.config_loader import load_tenant_config
from apps.shared.utils.logger import get_logger
from apps.shared.utils.pagination import PaginationRequest

logger = get_logger(__name__)

PARSED_CONTENT_BLOCK_LIMIT = 200


class DocumentService(TenantAwareService):
    """Service for handling document operations.

    Document access is inherited from collection-level authz via DocumentCollectionService.
    """

    def __init__(
        self,
        tenant_id: int,
        db_session: AsyncSession,
        file_storage: FileStorage,
    ):
        super().__init__(tenant_id, db_session=db_session)
        self.document_repo = DBDocumentRepository(db_session)
        self.file_storage = file_storage
        self._collection_service = DocumentCollectionService(tenant_id, db_session)
        self._resource_index_service: ResourceIndexService | None = None
        self._resource_index_repo: ResourceIndexRepository | None = None
        self._tenant_config: dict | None = None
        self._tenant_config_loaded = False

    def _get_resource_index_repo(self) -> ResourceIndexRepository:
        if self._resource_index_repo is None:
            self._resource_index_repo = ResourceIndexRepository(self.db_session)
        return self._resource_index_repo

    async def _load_tenant_config(self) -> dict | None:
        if not self._tenant_config_loaded:
            self._tenant_config = await load_tenant_config(self.db_session, self.tenant_id)
            self._tenant_config_loaded = True
        return self._tenant_config

    async def _get_resource_index_service(self) -> ResourceIndexService:
        if self._resource_index_service is None:
            self._resource_index_service = ResourceIndexService(
                tenant_id=self.tenant_id,
                db_session=self.db_session,
                file_storage=self.file_storage,
                tenant_config=await self._load_tenant_config(),
            )
        return self._resource_index_service

    @staticmethod
    def _duplicate_content_message(
        upload_filename: str,
        existing_filename: str,
        *,
        upload_date=None,
    ) -> str:
        return DocumentIntake.duplicate_content_message(
            upload_filename,
            existing_filename,
            upload_date=upload_date,
        )

    @staticmethod
    def _actor(requester_id: int, requester_role: str | None, tenant_id: int) -> ActorContext:
        return ActorContext(tenant_id=tenant_id, user_id=requester_id, user_role=requester_role)

    async def list_documents(
        self,
        requester_id: int,
        requester_role: str,
        page: int = 1,
        page_size: int = 10,
        query: str | None = None,
        collection_id: int | None = None,
    ) -> tuple[list[DocumentInfo], PaginationRequest]:
        """List documents for the tenant with optional pagination."""
        logger.debug(
            "Listing documents for tenant: %s, page=%s, page_size=%s, collection_id=%s",
            self.tenant_id,
            page,
            page_size,
            collection_id,
        )
        normalized_query = query.strip() if query else None
        actor = self._actor(requester_id, requester_role, self.tenant_id)

        if collection_id is not None:
            await self._collection_service.require_collection_access(
                collection_id=collection_id,
                actor=actor,
                action=ABAC_ACTION_READ,
            )

        access_scope = await self._collection_service.build_document_access_scope(
            actor=actor,
            action=ABAC_ACTION_READ,
        )
        if access_scope.deny_all:
            pagination = PaginationRequest.with_total(page=page, page_size=page_size, total=0)
            return [], pagination

        abac_filter = access_scope.document_filter

        if normalized_query:
            total = await self.document_repo.count_by_tenant_with_query(
                self.tenant_id,
                normalized_query,
                collection_id=collection_id,
                abac_filter=abac_filter,
            )
        else:
            total = await self.document_repo.count_by_tenant(
                self.tenant_id,
                collection_id=collection_id,
                abac_filter=abac_filter,
            )

        if total == 0:
            pagination = PaginationRequest.with_total(page=page, page_size=page_size, total=0)
            return [], pagination

        pagination = PaginationRequest.with_total(page=page, page_size=page_size, total=total)

        docs = await self.document_repo.list_with_search(
            self.tenant_id,
            query=normalized_query,
            collection_id=collection_id,
            limit=pagination.page_size,
            offset=pagination.offset,
            abac_filter=abac_filter,
        )

        doc_ids = [d.id for d in docs]
        resource_index_map = await self._get_resource_index_repo().list_by_resources(
            self.tenant_id,
            RESOURCE_TYPE_DOCUMENT,
            doc_ids,
        )

        drive_linked_ids: set[int] = set()
        if collection_id is not None and doc_ids:
            drive_linked_ids = await DocumentSyncRepository(self.db_session).list_drive_linked_document_ids(
                self.tenant_id,
                collection_id,
                document_ids=doc_ids,
            )

        documents = []
        for doc in docs:
            domain = db_document_to_domain(doc, resource_index_map.get(doc.id))
            if doc.id in drive_linked_ids:
                domain.intake_source = "drive_sync"
            documents.append(domain_document_to_api(domain))
        return documents, pagination

    async def upload_document(
        self,
        file: UploadFile,
        owner_id: int,
        requester_role: str | None,
        collection_id: int,
    ) -> DocumentDomain:
        """Upload a document into a collection."""
        logger.info("Uploading document %s for tenant: %s collection: %s", file.filename, self.tenant_id, collection_id)
        actor = self._actor(owner_id, requester_role, self.tenant_id)
        await self._collection_service.require_collection_access(
            collection_id=collection_id,
            actor=actor,
            action=ABAC_ACTION_WRITE,
        )

        file_content = await file.read()
        intake = DocumentIntake(self.tenant_id, self.db_session, self.file_storage)
        return await intake.persist(
            IntakeRequest(
                collection_id=collection_id,
                filename=file.filename,
                content=file_content,
                owner_id=owner_id,
                source="upload",
                on_duplicate="error",
            )
        )

    async def queue_document_reparse(self, document_id: int, *, triggered_by: str = "api") -> DocumentDomain:
        parse_pipeline = DocumentParsePipeline(self.tenant_id, self.db_session, self.file_storage)
        await parse_pipeline.queue_document_reparse(document_id, triggered_by=triggered_by)
        return await self._get_document_domain(document_id)

    async def queue_document_reindex(self, document_id: int) -> DocumentDomain:
        document_db = await self.document_repo.get_by_id_and_tenant(document_id, self.tenant_id)
        if not document_db:
            raise ResourceNotFoundError(f"Document not found: {document_id}")

        marked = await self._get_resource_index_repo().mark_document_vector_stale(self.tenant_id, document_id)
        if not marked:
            raise ValidationError("Document has no parsed content to re-index.")

        logger.info(
            "document_reindex_queued tenant_id=%s document_id=%s",
            self.tenant_id,
            document_id,
        )
        return await self._get_document_domain(document_id)

    async def queue_collection_reparse(
        self,
        collection_id: int,
        requester_id: int,
        requester_role: str | None,
        *,
        triggered_by: str = "api",
    ) -> DocumentQueueResponse:
        await self._collection_service.require_collection_access(
            collection_id=collection_id,
            actor=self._actor(requester_id, requester_role, self.tenant_id),
            action=ABAC_ACTION_WRITE,
        )
        parse_pipeline = DocumentParsePipeline(self.tenant_id, self.db_session, self.file_storage)
        queued_count = await parse_pipeline.queue_collection_reparse(collection_id, triggered_by=triggered_by)
        logger.info(
            "collection_reparse_queued tenant_id=%s collection_id=%s queued_count=%s",
            self.tenant_id,
            collection_id,
            queued_count,
        )
        return DocumentQueueResponse(queued_count=queued_count)

    async def queue_collection_reindex(
        self,
        collection_id: int,
        requester_id: int,
        requester_role: str | None,
    ) -> DocumentQueueResponse:
        await self._collection_service.require_collection_access(
            collection_id=collection_id,
            actor=self._actor(requester_id, requester_role, self.tenant_id),
            action=ABAC_ACTION_WRITE,
        )
        total_count = len(await self.document_repo.list_ids_by_collection(self.tenant_id, collection_id))
        queued_count = await self._get_resource_index_repo().mark_collection_vectors_stale(
            self.tenant_id,
            collection_id,
        )
        logger.info(
            "collection_reindex_queued tenant_id=%s collection_id=%s queued_count=%s",
            self.tenant_id,
            collection_id,
            queued_count,
        )
        return DocumentQueueResponse(
            queued_count=queued_count,
            skipped_count=max(total_count - queued_count, 0),
        )

    async def _get_document_domain(self, document_id: int) -> DocumentDomain:
        document_db = await self.document_repo.get_by_id_and_tenant(document_id, self.tenant_id)
        if not document_db:
            raise ResourceNotFoundError(f"Document not found: {document_id}")
        resource_index = await self._get_resource_index_repo().get_by_resource(
            self.tenant_id,
            RESOURCE_TYPE_DOCUMENT,
            document_id,
        )
        return db_document_to_domain(document_db, resource_index)

    async def get_parsed_content(
        self,
        document_id: int,
        requester_id: int,
        requester_role: str,
    ) -> DocumentParsedContent:
        document_db = await self.document_repo.get_by_id_and_tenant(document_id, self.tenant_id)
        if not document_db:
            raise ResourceNotFoundError(f"Document not found: {document_id}")

        await self._collection_service.require_collection_access(
            collection_id=document_db.collection_id,
            actor=self._actor(requester_id, requester_role, self.tenant_id),
            action=ABAC_ACTION_READ,
        )

        resource_index = await self._get_resource_index_repo().get_by_resource(
            self.tenant_id,
            RESOURCE_TYPE_DOCUMENT,
            document_id,
        )
        parsed_at = resource_index.parsed_at.isoformat() if resource_index and resource_index.parsed_at else None
        parse_error = resource_index.parse_error if resource_index else None
        parser = resource_index.source_parser if resource_index else None
        storage_uri = get_storage_uri(resource_index.raw_content) if resource_index else None

        blocks: list[DocumentParsedBlock] = []
        type_counts: dict[str, int] = {}
        truncated = False
        if storage_uri:
            blocks_document = await read_blocks_json(
                self.file_storage,
                storage_uri,
                tenant_id=self.tenant_id,
            )
            raw_blocks = [block for block in blocks_document.get("blocks", []) if isinstance(block, dict)]
            type_counts = summarize_blocks(raw_blocks)
            truncated = len(raw_blocks) > PARSED_CONTENT_BLOCK_LIMIT
            parser = parser or blocks_document.get("parser")
            blocks = [_to_parsed_block(block) for block in raw_blocks[:PARSED_CONTENT_BLOCK_LIMIT]]

        return DocumentParsedContent(
            document_id=document_id,
            filename=document_db.filename,
            parser=parser,
            parsed_at=parsed_at,
            parse_error=parse_error,
            block_count=sum(type_counts.values()),
            truncated=truncated,
            type_counts=type_counts,
            blocks=blocks,
        )

    async def read_document_image(
        self,
        document_id: int,
        filename: str,
        requester_id: int,
        requester_role: str,
    ) -> DocumentImageFile:
        document_db = await self.document_repo.get_by_id_and_tenant(document_id, self.tenant_id)
        if not document_db:
            raise ResourceNotFoundError(f"Document not found: {document_id}")

        await self._collection_service.require_collection_access(
            collection_id=document_db.collection_id,
            actor=self._actor(requester_id, requester_role, self.tenant_id),
            action=ABAC_ACTION_READ,
        )

        relative_key = document_image_relative_key(document_id, filename)
        media_type = image_media_type(filename)
        if relative_key is None or media_type is None:
            raise ResourceNotFoundError(f"Image not found for document {document_id}: {filename}")

        resolved = resolve_storage_ref(self.tenant_id, relative_key)
        if not await self.file_storage.exists(resolved):
            raise ResourceNotFoundError(f"Image not found for document {document_id}: {filename}")
        return DocumentImageFile(await self.file_storage.read(resolved), media_type)

    async def delete_documents(
        self,
        doc_ids: list[int],
        requester_id: int,
        requester_role: str | None,
    ) -> dict:
        """Delete one or multiple documents."""
        logger.info("Deleting %s document(s) for tenant: %s", len(doc_ids), self.tenant_id)
        actor = self._actor(requester_id, requester_role, self.tenant_id)

        documents = []
        not_found_ids = []
        for doc_id in doc_ids:
            document_db = await self.document_repo.get_by_id_and_tenant(doc_id, self.tenant_id)
            if not document_db:
                not_found_ids.append(doc_id)
            else:
                await self._collection_service.require_collection_access(
                    collection_id=document_db.collection_id,
                    actor=actor,
                    action=ABAC_ACTION_WRITE,
                )
                documents.append((document_db, db_document_to_domain(document_db)))

        if not_found_ids:
            raise ResourceNotFoundError(f"Documents not found: {not_found_ids}")

        deleted_count = 0

        for document_db, document in documents:
            resource_index = await self._get_resource_index_repo().get_by_resource(
                self.tenant_id,
                RESOURCE_TYPE_DOCUMENT,
                document.id,
            )
            storage_uri = None
            if resource_index and resource_index.raw_content:
                from apps.shared.document.manifest import get_storage_uri

                storage_uri = get_storage_uri(resource_index.raw_content)

            await self.file_storage.delete(resolve_storage_ref(self.tenant_id, document.file_url))
            logger.info("File deleted from storage: %s", document.file_url)

            from apps.shared.document.manifest import delete_parsed_artifacts

            await delete_parsed_artifacts(
                self.file_storage,
                tenant_id=self.tenant_id,
                document_id=document.id,
                storage_uri=storage_uri,
            )

            delete_success = await self.document_repo.delete_document(document.id)
            if delete_success:
                deleted_count += 1
                logger.info("Document deleted successfully: %s", document.id)
                await self._delete_document_resource_index(document.id)
            else:
                raise InternalServiceError(f"Failed to delete document: {document.id}, {document.filename}")

        return {
            "message": f"Deleted {deleted_count} of {len(doc_ids)} documents",
            "deleted_count": deleted_count,
            "total_count": len(doc_ids),
        }

    async def _delete_document_resource_index(self, doc_id: int) -> None:
        try:
            deleted = await (await self._get_resource_index_service()).delete(RESOURCE_TYPE_DOCUMENT, doc_id)
            if deleted:
                logger.info(
                    "Removed resource index and vector entries for document %d (tenant=%s)",
                    doc_id,
                    self.tenant_id,
                )
        except Exception as exc:
            logger.warning("Failed to delete resource index for document %d: %s", doc_id, exc)


def _to_parsed_block(block: dict) -> DocumentParsedBlock:
    block_type = str(block.get("type") or "text")
    text = block.get("text")
    caption = block.get("caption")
    page = block.get("page")
    uri = block.get("uri")
    return DocumentParsedBlock(
        type=block_type,
        text=text if isinstance(text, str) else None,
        caption=caption if isinstance(caption, str) else None,
        page=page if isinstance(page, int) else None,
        uri=uri if block_type == "image" and isinstance(uri, str) else None,
    )
