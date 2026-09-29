"""Document parse pipeline — orchestrate parsing and persist artifacts."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.document.adapters import db_document_to_domain
from apps.shared.document.domain import DocumentDomain
from apps.shared.document.manifest import (
    build_manifest_pointer,
    compute_content_hash,
    delete_parsed_artifacts,
    get_storage_uri,
    persist_parse_images,
    summarize_blocks,
    try_read_existing_blocks,
    write_blocks_json,
)
from apps.shared.document.parsers.registry import get_parser_registry
from apps.shared.document.repository import DBDocumentRepository
from apps.shared.document.types import (
    DocumentParseWorkerResult,
    DocumentProcessOutcome,
    DocumentStatus,
    ParseIssueRow,
    ParseJobStatus,
    ParseStatusSnapshot,
    PollJobOutcome,
    PollPendingResult,
    ProcessPendingResult,
)
from apps.shared.domain.types import RESOURCE_TYPE_DOCUMENT
from apps.shared.infra.storage import FileStorage
from apps.shared.search.repository import ResourceIndexRepository
from apps.shared.search.schemas import ResourceIndexCreateDTO
from apps.shared.tenant.config_loader import load_tenant_config
from apps.shared.utils.logger import get_logger

logger = get_logger(__name__)

SessionFactory = Callable[[], AbstractAsyncContextManager[AsyncSession]]


class DocumentParsePipeline:
    """Orchestrate document parsing and persist artifacts to storage."""

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
        self._registry = get_parser_registry(file_storage)
        self._tenant_config: dict | None = None
        self._tenant_config_loaded = False

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

    async def initialize_resource_index(self, doc: DocumentDomain) -> None:
        await (await self._index_service()).create_or_update(
            ResourceIndexCreateDTO(
                tenant_id=self.tenant_id,
                resource_type=RESOURCE_TYPE_DOCUMENT,
                resource_id=doc.id,
                owner_id=doc.owner_id,
                parent_id=doc.collection_id,
                raw_content=None,
                content_updated_at=doc.upload_date,
                source_parser=self._registry.configured_parser_name(),
            )
        )

    async def enqueue_document_parse(self, doc: DocumentDomain, *, triggered_by: str = "upload") -> None:
        """Mark document for background parsing."""
        await self._document_repo.update_status(doc.id, DocumentStatus.PROCESSING)
        logger.info(
            "document_parse_enqueued tenant_id=%s document_id=%s triggered_by=%s",
            self.tenant_id,
            doc.id,
            triggered_by,
        )

    async def _list_pending_parse_ids(self, *, limit: int = 10) -> list[int]:
        docs = await self._document_repo.list_pending_parse(self.tenant_id, limit=limit)
        return [doc.id for doc in docs]

    async def _list_pending_parse_job_ids(self, *, limit: int = 10) -> list[int]:
        records = await self._resource_index_repo.list_pending_parse_jobs(self.tenant_id, limit=limit)
        return [record.resource_id for record in records]

    async def list_parse_target_ids(
        self,
        *,
        document_id: int | None = None,
        collection_id: int | None = None,
        failed_only: bool = False,
    ) -> list[int]:
        return await self._document_repo.list_parse_target_ids(
            self.tenant_id,
            document_id=document_id,
            collection_id=collection_id,
            failed_only=failed_only,
        )

    async def parse_status_snapshot(self) -> ParseStatusSnapshot:
        documents = [
            {"tenant_id": self.tenant_id, "status": status, "count": count}
            for status, count in await self._document_repo.count_statuses(self.tenant_id)
        ]
        vector_index = [
            {"tenant_id": self.tenant_id, "vector_status": vector_status, "count": count}
            for vector_status, count in await self._resource_index_repo.document_vector_status_by_tenant(self.tenant_id)
        ]
        return {
            "documents": documents,
            "parse_index": await self._resource_index_repo.document_parse_status_by_tenant(self.tenant_id),
            "vector_index": vector_index,
        }

    async def list_parse_issues(self, *, limit: int = 20) -> list[ParseIssueRow]:
        return await self._document_repo.list_parse_issues(self.tenant_id, limit=limit)

    async def process_document_by_id(
        self,
        document_id: int,
        *,
        triggered_by: str = "worker",
    ) -> DocumentProcessOutcome | None:
        document_db = await self._document_repo.get_by_id_and_tenant(document_id, self.tenant_id)
        if document_db is None:
            return None
        return await self.process_document(db_document_to_domain(document_db), triggered_by=triggered_by)

    async def run_pending(
        self,
        *,
        session_factory: SessionFactory,
        batch_size: int = 10,
        triggered_by: str = "worker",
    ) -> DocumentParseWorkerResult:
        """Submit queued parses, then poll in-flight async jobs."""
        process_result = await self._process_pending(
            session_factory=session_factory,
            batch_size=batch_size,
            triggered_by=triggered_by,
        )
        poll_result = await self._poll_pending(
            session_factory=session_factory,
            batch_size=batch_size,
        )
        return {
            "queued": process_result["processed"],
            "completed": process_result["completed"] + poll_result["completed"],
            "submitted": process_result["submitted"],
            "failed": process_result["failed"] + poll_result["failed"],
            "polled": poll_result["polled"],
        }

    async def _process_pending(
        self,
        *,
        session_factory: SessionFactory,
        batch_size: int = 10,
        triggered_by: str = "worker",
    ) -> ProcessPendingResult:
        document_ids = await self._list_pending_parse_ids(limit=batch_size)
        completed = 0
        failed = 0
        submitted = 0
        for document_id in document_ids:
            async with session_factory() as session:
                processing = type(self)(self.tenant_id, session, self.file_storage)
                try:
                    outcome = await processing.process_document_by_id(document_id, triggered_by=triggered_by)
                    if outcome is None:
                        continue
                    if outcome == DocumentProcessOutcome.SUBMITTED:
                        submitted += 1
                    else:
                        completed += 1
                except Exception as exc:
                    failed += 1
                    logger.warning(
                        "document_parse_failed tenant_id=%s document_id=%s error=%s",
                        self.tenant_id,
                        document_id,
                        exc,
                    )

        return {
            "processed": len(document_ids),
            "completed": completed,
            "submitted": submitted,
            "failed": failed,
        }

    async def process_document(self, doc: DocumentDomain, *, triggered_by: str = "worker") -> DocumentProcessOutcome:
        parser = self._registry.get()
        logger.info(
            "document_parse_started tenant_id=%s document_id=%s parser=%s triggered_by=%s",
            self.tenant_id,
            doc.id,
            parser.name,
            triggered_by,
        )
        await self._document_repo.update_status(doc.id, DocumentStatus.PROCESSING)
        started = datetime.now(UTC)
        try:
            recovered = await self._try_complete_from_existing_blocks(doc, parser.name)
            if recovered:
                logger.info(
                    "document_parse_recovered tenant_id=%s document_id=%s parser=%s",
                    self.tenant_id,
                    doc.id,
                    parser.name,
                )
                return DocumentProcessOutcome.COMPLETED

            if parser.is_async:
                submission = await parser.submit(doc)
                await self._resource_index_repo.update_parse_submitted(
                    self.tenant_id,
                    RESOURCE_TYPE_DOCUMENT,
                    doc.id,
                    parse_job_id=submission.job_id,
                    source_parser=parser.name,
                )
                return DocumentProcessOutcome.SUBMITTED

            blocks_document = await parser.parse(doc)
            await self._persist_blocks(doc, blocks_document, parser.name)
            await self._document_repo.update_status(doc.id, DocumentStatus.ACTIVE)
            elapsed_ms = int((datetime.now(UTC) - started).total_seconds() * 1000)
            logger.info(
                "document_parse_completed tenant_id=%s document_id=%s parser=%s duration_ms=%s block_summary=%s",
                self.tenant_id,
                doc.id,
                parser.name,
                elapsed_ms,
                summarize_blocks(blocks_document.get("blocks", [])),
            )
            return DocumentProcessOutcome.COMPLETED
        except Exception as exc:
            await self._mark_failed(doc, parser.name, str(exc))
            raise

    async def queue_collection_reparse(self, collection_id: int, *, triggered_by: str = "api") -> int:
        document_ids = await self._document_repo.list_ids_by_collection(self.tenant_id, collection_id)
        for document_id in document_ids:
            await self.queue_document_reparse(document_id, triggered_by=triggered_by)
        return len(document_ids)

    async def queue_document_reparse(self, document_id: int, *, triggered_by: str = "api") -> None:
        document_db = await self._document_repo.get_by_id_and_tenant(document_id, self.tenant_id)
        if not document_db:
            raise ValueError(f"Document not found: {document_id}")

        doc = db_document_to_domain(document_db)
        existing_index = await self._resource_index_repo.get_by_resource(
            self.tenant_id,
            RESOURCE_TYPE_DOCUMENT,
            document_id,
        )
        if existing_index and existing_index.raw_content:
            await delete_parsed_artifacts(
                self.file_storage,
                tenant_id=self.tenant_id,
                document_id=document_id,
                storage_uri=get_storage_uri(existing_index.raw_content),
            )

        await self._resource_index_repo.reset_parse_state(
            self.tenant_id,
            RESOURCE_TYPE_DOCUMENT,
            document_id,
        )

        logger.info(
            "document_reparse_queued tenant_id=%s document_id=%s triggered_by=%s",
            self.tenant_id,
            document_id,
            triggered_by,
        )
        await self.enqueue_document_parse(doc, triggered_by=triggered_by)

    async def _poll_pending(
        self,
        *,
        session_factory: SessionFactory,
        batch_size: int = 10,
    ) -> PollPendingResult:
        resource_ids = await self._list_pending_parse_job_ids(limit=batch_size)
        completed = 0
        failed = 0
        for resource_id in resource_ids:
            async with session_factory() as session:
                outcome = await type(self)(self.tenant_id, session, self.file_storage).poll_one_job(resource_id)
                if outcome == PollJobOutcome.COMPLETED:
                    completed += 1
                elif outcome == PollJobOutcome.FAILED:
                    failed += 1

        return {"completed": completed, "failed": failed, "polled": len(resource_ids)}

    async def poll_one_job(self, resource_id: int) -> PollJobOutcome:
        record = await self._resource_index_repo.get_by_resource(
            self.tenant_id,
            RESOURCE_TYPE_DOCUMENT,
            resource_id,
        )
        if record is None or not record.parse_job_id or record.parsed_at is not None:
            return PollJobOutcome.SKIPPED

        parser = self._registry.get(record.source_parser)
        if not parser.is_async:
            error = "Parser is not async or parse_job_id is missing"
            logger.warning(
                "document_parse_failed tenant_id=%s document_id=%s parser=%s error=%s",
                self.tenant_id,
                resource_id,
                parser.name,
                error,
            )
            await self._resource_index_repo.update_parse_failed(
                self.tenant_id,
                RESOURCE_TYPE_DOCUMENT,
                resource_id,
                error=error,
                parse_error_at=datetime.now(UTC),
            )
            return PollJobOutcome.FAILED

        document_db = await self._document_repo.get_by_id(resource_id)
        if not document_db:
            error = "Document not found for pending parse job"
            logger.warning(
                "document_parse_failed tenant_id=%s document_id=%s parser=%s error=%s",
                self.tenant_id,
                resource_id,
                parser.name,
                error,
            )
            await self._resource_index_repo.update_parse_failed(
                self.tenant_id,
                RESOURCE_TYPE_DOCUMENT,
                resource_id,
                error=error,
                parse_error_at=datetime.now(UTC),
            )
            return PollJobOutcome.FAILED

        doc = db_document_to_domain(document_db)
        try:
            status = await parser.poll(record.parse_job_id)
            if ParseJobStatus.is_in_progress(status):
                return PollJobOutcome.PENDING
            if status != ParseJobStatus.COMPLETED:
                recovered = await self._try_complete_from_existing_blocks(doc, parser.name)
                if recovered:
                    logger.info(
                        "document_parse_recovered tenant_id=%s document_id=%s parser=%s",
                        self.tenant_id,
                        doc.id,
                        parser.name,
                    )
                    return PollJobOutcome.COMPLETED
                error = f"Async parse job failed: {status}"
                await self._mark_failed(doc, parser.name, error)
                logger.warning(
                    "document_parse_failed tenant_id=%s document_id=%s parser=%s error=%s",
                    self.tenant_id,
                    doc.id,
                    parser.name,
                    error,
                )
                return PollJobOutcome.FAILED

            blocks_document = await parser.fetch_result(doc, record.parse_job_id)
            await self._persist_blocks(doc, blocks_document, parser.name)
            await self._document_repo.update_status(doc.id, DocumentStatus.ACTIVE)
            logger.info(
                "document_parse_completed tenant_id=%s document_id=%s parser=%s block_summary=%s",
                self.tenant_id,
                doc.id,
                parser.name,
                summarize_blocks(blocks_document.get("blocks", [])),
            )
            return PollJobOutcome.COMPLETED
        except Exception as exc:
            recovered = await self._try_complete_from_existing_blocks(doc, parser.name)
            if recovered:
                logger.info(
                    "document_parse_recovered tenant_id=%s document_id=%s parser=%s",
                    self.tenant_id,
                    doc.id,
                    parser.name,
                )
                return PollJobOutcome.COMPLETED
            await self._mark_failed(doc, parser.name, str(exc))
            logger.warning(
                "document_parse_failed tenant_id=%s document_id=%s parser=%s error=%s",
                self.tenant_id,
                doc.id,
                parser.name,
                exc,
            )
            return PollJobOutcome.FAILED

    async def _try_complete_from_existing_blocks(self, doc: DocumentDomain, parser_name: str) -> bool:
        blocks_document = await try_read_existing_blocks(
            self.file_storage,
            tenant_id=self.tenant_id,
            document_id=doc.id,
        )
        if not blocks_document:
            return False
        try:
            await self._persist_blocks(doc, blocks_document, parser_name)
            await self._document_repo.update_status(doc.id, DocumentStatus.ACTIVE)
            return True
        except Exception as exc:
            logger.warning(
                "document_parse_recover_failed tenant_id=%s document_id=%s error=%s",
                self.tenant_id,
                doc.id,
                exc,
            )
            return False

    async def _persist_blocks(self, doc: DocumentDomain, blocks_document: dict, parser_name: str) -> None:
        blocks = await persist_parse_images(
            self.file_storage,
            tenant_id=self.tenant_id,
            document_id=doc.id,
            blocks=[block for block in blocks_document.get("blocks", []) if isinstance(block, dict)],
        )
        blocks_document = {**blocks_document, "blocks": blocks}
        storage_uri = await write_blocks_json(
            self.file_storage,
            tenant_id=self.tenant_id,
            document_id=doc.id,
            blocks_document=blocks_document,
        )
        owner_id = doc.owner_id
        if owner_id is None:
            existing = await self._resource_index_repo.get_by_resource(
                self.tenant_id,
                RESOURCE_TYPE_DOCUMENT,
                doc.id,
            )
            owner_id = existing.owner_id if existing is not None else None
        if owner_id is None:
            raise ValueError("Cannot persist parse artifacts without owner_id")
        content_hash = compute_content_hash(blocks_document)
        manifest = build_manifest_pointer(
            storage_uri=storage_uri,
            content_hash=content_hash,
            block_summary=summarize_blocks(blocks_document.get("blocks", [])),
            filename=doc.filename,
            parser=parser_name,
        )
        await (await self._index_service()).create_or_update(
            ResourceIndexCreateDTO(
                tenant_id=self.tenant_id,
                resource_type=RESOURCE_TYPE_DOCUMENT,
                resource_id=doc.id,
                owner_id=owner_id,
                parent_id=doc.collection_id,
                raw_content=manifest,
                content_updated_at=datetime.now(UTC),
                source_parser=parser_name,
            )
        )
        await self._resource_index_repo.update_parse_completed(
            self.tenant_id,
            RESOURCE_TYPE_DOCUMENT,
            doc.id,
            parsed_at=datetime.now(UTC),
        )

    async def _mark_failed(self, doc: DocumentDomain, parser_name: str, error: str) -> None:
        await self._document_repo.update_status(doc.id, DocumentStatus.FAILED)
        await self._resource_index_repo.update_parse_failed(
            self.tenant_id,
            RESOURCE_TYPE_DOCUMENT,
            doc.id,
            error=error[:1000],
            parse_error_at=datetime.now(UTC),
        )
