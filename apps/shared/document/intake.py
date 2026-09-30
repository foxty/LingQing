"""Document intake pipeline — persist bytes and register for parsing."""

from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.core.exceptions import DuplicateResourceError
from apps.shared.document.adapters import db_document_to_domain
from apps.shared.document.domain import DocumentDomain
from apps.shared.document.manifest import document_original_relative_key, normalize_document_filename
from apps.shared.document.parsers.registry import get_parser_registry
from apps.shared.document.repository import DBDocumentRepository
from apps.shared.document.types import DocumentStatus, IntakeSource
from apps.shared.domain.types import RESOURCE_TYPE_DOCUMENT
from apps.shared.infra.storage import FileStorage
from apps.shared.infra.storage.paths import normalize_storage_key
from apps.shared.search.repository import ResourceIndexRepository
from apps.shared.search.schemas import ResourceIndexCreateDTO
from apps.shared.tenant.config_loader import load_tenant_config
from apps.shared.utils.logger import get_logger

logger = get_logger(__name__)

DuplicatePolicy = Literal["error", "skip", "update"]


@dataclass(frozen=True)
class IntakeRequest:
    """Request to persist a document file into tenant storage and metadata."""

    collection_id: int
    filename: str
    content: bytes
    owner_id: int
    source: IntakeSource = "upload"
    on_duplicate: DuplicatePolicy = "error"


class DocumentIntake:
    """Persist uploaded or synced file bytes and register the document for parsing."""

    def __init__(
        self,
        tenant_id: int,
        db_session: AsyncSession,
        file_storage: FileStorage,
    ):
        self.tenant_id = tenant_id
        self.db_session = db_session
        self.file_storage = file_storage
        self._document_repo = DBDocumentRepository(db_session)
        self._resource_index_repo = ResourceIndexRepository(db_session)
        self._tenant_config: dict | None = None
        self._tenant_config_loaded = False

    @staticmethod
    def calculate_file_hash(content: bytes) -> str:
        return hashlib.sha256(content).hexdigest()

    @staticmethod
    def duplicate_content_message(
        upload_filename: str,
        existing_filename: str,
        *,
        upload_date: datetime | None = None,
    ) -> str:
        """Build a user-facing duplicate-content error for collection uploads."""
        if upload_filename == existing_filename:
            message = f"该集合中已存在相同内容的文件 '{existing_filename}'"
        else:
            message = f"文件 '{upload_filename}' 与已上传的文件 '{existing_filename}' 内容相同，无法重复上传"
        if upload_date is not None:
            return f"{message}（已存在文件上传于 {upload_date.isoformat()}）。"
        return f"{message}。"

    async def persist(self, request: IntakeRequest) -> DocumentDomain:
        """Save file content, create document metadata, and register for parse pipeline."""
        file_hash = self.calculate_file_hash(request.content)
        existing_doc = await self._document_repo.find_by_hash(
            self.tenant_id,
            file_hash,
            request.collection_id,
        )
        if existing_doc:
            if request.on_duplicate == "skip":
                resource_index = await self._resource_index_repo.get_by_resource(
                    self.tenant_id,
                    RESOURCE_TYPE_DOCUMENT,
                    existing_doc.id,
                )
                return db_document_to_domain(existing_doc, resource_index)
            if request.on_duplicate == "error":
                logger.warning(
                    "Duplicate file detected: %s (hash=%s..., collection_id=%s, existing_doc_id=%s)",
                    request.filename,
                    file_hash[:8],
                    request.collection_id,
                    existing_doc.id,
                )
                raise DuplicateResourceError(
                    self.duplicate_content_message(
                        request.filename,
                        existing_doc.filename,
                        upload_date=existing_doc.upload_date,
                    )
                )

        file_size = len(request.content)
        stored_filename = normalize_document_filename(request.filename)

        document_domain = DocumentDomain.create_new(
            tenant_id=self.tenant_id,
            collection_id=request.collection_id,
            filename=stored_filename,
            file_url=stored_filename,
            file_size=file_size,
            file_hash=file_hash,
            owner_id=request.owner_id,
        )

        try:
            document_db = await self._document_repo.create_document(document_domain)
        except IntegrityError as exc:
            logger.warning(
                "Concurrent duplicate intake detected: %s (hash=%s..., collection_id=%s)",
                request.filename,
                file_hash[:8],
                request.collection_id,
            )
            raise DuplicateResourceError(self.duplicate_content_message(request.filename, request.filename)) from exc

        relative_key = document_original_relative_key(document_db.id, stored_filename)
        storage_key = await self.file_storage.save(
            str(self.tenant_id),
            relative_key,
            io.BytesIO(request.content),
        )
        file_url = normalize_storage_key(self.tenant_id, storage_key)
        logger.info(
            "document_intake_saved tenant_id=%s collection_id=%s document_id=%s file_url=%s size=%s source=%s",
            self.tenant_id,
            request.collection_id,
            document_db.id,
            file_url,
            file_size,
            request.source,
        )

        document_db = await self._document_repo.update_document_file(
            document_db.id,
            self.tenant_id,
            filename=stored_filename,
            file_url=file_url,
            file_size=file_size,
            file_hash=file_hash,
        )
        document_domain = db_document_to_domain(document_db)

        try:
            await self._register_for_parse(document_domain, triggered_by=request.source)
        except Exception as exc:
            logger.warning(
                "Failed to register document for parse tenant_id=%s document_id=%s error=%s",
                self.tenant_id,
                document_domain.id,
                exc,
            )

        document_db = await self._document_repo.get_by_id_and_tenant(document_domain.id, self.tenant_id)
        resource_index = await self._resource_index_repo.get_by_resource(
            self.tenant_id,
            RESOURCE_TYPE_DOCUMENT,
            document_domain.id,
        )
        return db_document_to_domain(document_db, resource_index)

    async def _register_for_parse(self, doc: DocumentDomain, *, triggered_by: str) -> None:
        await self._create_resource_index_stub(doc)
        await self._document_repo.update_status(doc.id, DocumentStatus.PROCESSING)
        logger.info(
            "document_parse_enqueued tenant_id=%s document_id=%s triggered_by=%s",
            self.tenant_id,
            doc.id,
            triggered_by,
        )

    async def _create_resource_index_stub(self, doc: DocumentDomain) -> None:
        registry = get_parser_registry(self.file_storage)
        index_service = await self._index_service()
        await index_service.create_or_update(
            ResourceIndexCreateDTO(
                tenant_id=self.tenant_id,
                resource_type=RESOURCE_TYPE_DOCUMENT,
                resource_id=doc.id,
                owner_id=doc.owner_id,
                parent_id=doc.collection_id,
                raw_content=None,
                content_updated_at=doc.upload_date,
                source_parser=registry.configured_parser_name(),
            )
        )

    async def _load_tenant_config(self) -> dict | None:
        if not self._tenant_config_loaded:
            self._tenant_config = await load_tenant_config(self.db_session, self.tenant_id)
            self._tenant_config_loaded = True
        return self._tenant_config

    async def _index_service(self):
        from apps.shared.search.indexing_service import ResourceIndexService

        return ResourceIndexService(
            tenant_id=self.tenant_id,
            db_session=self.db_session,
            file_storage=self.file_storage,
            tenant_config=await self._load_tenant_config(),
        )
