"""Database-backed Document Repository."""

from datetime import UTC, datetime

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.sql.elements import ColumnElement

from apps.shared.db.base_repository import BaseRepository
from apps.shared.db.models import Document, DocumentCollection, ResourceIndex
from apps.shared.document.adapters import domain_collection_to_db_model, domain_document_to_db_model
from apps.shared.document.domain import DocumentCollectionDomain, DocumentDomain
from apps.shared.document.types import DocumentStatus, ParseIssueRow
from apps.shared.domain.types import RESOURCE_TYPE_DOCUMENT
from apps.shared.utils.logger import get_logger

_ACTIVE_STATUSES = (DocumentStatus.PROCESSING.value, DocumentStatus.ACTIVE.value)

logger = get_logger(__name__)


class DBDocumentRepository(BaseRepository[Document]):
    """Database-backed document repository.

    Handles document metadata storage in the database.
    File storage operations are handled by the service layer.

    Returns DB models (Document). Callers are responsible for converting to domain models.
    """

    def __init__(self, db: AsyncSession):
        """Initialize document repository.

        Args:
            db: Database session
        """
        super().__init__(Document, db)

    async def list_by_tenant(
        self,
        tenant_id: int,
        status: str | None = None,
        collection_id: int | None = None,
        limit: int | None = None,
        offset: int | None = None,
        abac_filter=None,
    ) -> list[Document]:
        """List documents for a tenant.

        Args:
            tenant_id: Tenant ID
            status: Optional status filter (processing, active, deleted)
            limit: Maximum number of results
            offset: Offset for pagination

        Returns:
            List of Document DB models
        """
        query = select(Document).where(Document.tenant_id == tenant_id)

        if status:
            query = query.where(Document.status == status)

        if collection_id is not None:
            query = query.where(Document.collection_id == collection_id)

        if abac_filter is not None:
            query = query.where(abac_filter)

        query = query.order_by(Document.upload_date.desc()).options(selectinload(Document.owner_user))

        if offset:
            query = query.offset(offset)
        if limit:
            query = query.limit(limit)

        result = await self.db.execute(query)
        return result.scalars().all()

    async def list_with_search(
        self,
        tenant_id: int,
        query: str | None = None,
        collection_id: int | None = None,
        limit: int | None = None,
        offset: int | None = None,
        abac_filter=None,
    ) -> list[Document]:
        """List documents for a tenant with optional search filter.

        Args:
            tenant_id: Tenant ID
            query: Optional search query (ILIKE-based substring match)
            limit: Maximum number of results
            offset: Offset for pagination
            abac_filter: Optional ABAC filter clause

        Returns:
            List of Document DB models
        """
        stmt = select(Document).where(Document.tenant_id == tenant_id).options(selectinload(Document.owner_user))

        if collection_id is not None:
            stmt = stmt.where(Document.collection_id == collection_id)

        if query:
            normalized_query = query.strip()
            if normalized_query:
                pattern = f"%{normalized_query}%"
                stmt = stmt.where(Document.filename.ilike(pattern))

        if abac_filter is not None:
            stmt = stmt.where(abac_filter)

        stmt = stmt.order_by(Document.upload_date.desc())

        if offset:
            stmt = stmt.offset(offset)
        if limit:
            stmt = stmt.limit(limit)

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_by_id_and_tenant(self, doc_id: int, tenant_id: int) -> Document | None:
        """Get document by ID and tenant ID.

        Args:
            doc_id: Document ID
            tenant_id: Tenant ID

        Returns:
            Document DB model or None if not found
        """
        result = await self.db.execute(select(Document).where(Document.id == doc_id, Document.tenant_id == tenant_id))
        return result.scalar_one_or_none()

    async def find_by_hash(self, tenant_id: int, file_hash: str, collection_id: int) -> Document | None:
        """Find document by file hash within a collection for deduplication."""
        result = await self.db.execute(
            select(Document).where(
                Document.tenant_id == tenant_id,
                Document.collection_id == collection_id,
                Document.file_hash == file_hash,
                Document.status.in_(_ACTIVE_STATUSES),
            )
        )
        return result.scalar_one_or_none()

    async def create_document(
        self,
        document_domain: DocumentDomain,
    ) -> Document:
        """Create document metadata record.

        Uses flush() to persist changes within the current transaction.
        The caller is responsible for commit/rollback (typically via @transaction).

        Args:
            document_domain: DocumentDomain to persist

        Returns:
            Created Document DB model (flushed but not committed)

        Note:
            This method uses flush() not commit(). Wrap in @transaction for atomicity.
        """
        logger.info(
            f"Creating document record for tenant={document_domain.tenant_id}, filename={document_domain.filename}"
        )

        # Create database record
        document = domain_document_to_db_model(document_domain)

        self.db.add(document)
        await self.db.flush()  # Get ID but don't commit
        await self.db.refresh(document)

        logger.info(f"Document record prepared: id={document.id}, filename={document.filename}")
        return document

    async def update_status(self, doc_id: int, status: DocumentStatus | str) -> Document | None:
        """Update document status."""
        resolved = status.value if isinstance(status, DocumentStatus) else status
        document = await self.get_by_id(doc_id)
        if not document:
            logger.warning(f"Document not found: id={doc_id}")
            return None

        document.status = resolved
        await self.db.flush()
        await self.db.refresh(document)

        logger.info(f"Document status updated (flushed): id={doc_id}, status={resolved}")
        return document

    async def update_document_file(
        self,
        doc_id: int,
        tenant_id: int,
        *,
        filename: str,
        file_url: str,
        file_size: int,
        file_hash: str,
    ) -> Document | None:
        """Update stored file metadata after an external sync refresh."""
        document = await self.get_by_id_and_tenant(doc_id, tenant_id)
        if not document:
            logger.warning("Document not found for file update: id=%s tenant_id=%s", doc_id, tenant_id)
            return None

        document.filename = filename
        document.file_url = file_url
        document.file_size = file_size
        document.file_hash = file_hash
        document.upload_date = datetime.now(UTC)
        await self.db.flush()
        await self.db.refresh(document)
        logger.info("Document file metadata updated: id=%s filename=%s", doc_id, filename)
        return document

    async def soft_delete(self, doc_id: int, tenant_id: int | None = None) -> bool:
        """Soft delete document (mark as deleted).

        Uses flush() to persist changes within the current transaction.
        Wrap in @transaction or manually commit for persistence.

        Args:
            doc_id: Document ID
            tenant_id: When set, scope lookup to this tenant

        Returns:
            True if successful, False if not found
        """
        if tenant_id is not None:
            document = await self.get_by_id_and_tenant(doc_id, tenant_id)
        else:
            document = await self.get_by_id(doc_id)
        if not document:
            return False

        document.status = DocumentStatus.DELETED.value
        await self.db.flush()

        logger.info(f"Document soft deleted (flushed): id={doc_id}")
        return True

    async def delete_document(self, doc_id: int) -> bool:
        """Delete document metadata record.

        Uses flush() to persist deletion within the current transaction.
        Wrap in @transaction or manually commit for persistence.

        Args:
            doc_id: Document ID

        Returns:
            True if successful, False if not found

        Note:
            File deletion should be handled by the service layer.
            This method only deletes the database record.
        """
        document = await self.get_by_id(doc_id)
        if not document:
            logger.warning(f"Document not found: id={doc_id}")
            return False

        # Delete database record (flush, not commit)
        await self.db.delete(document)
        await self.db.flush()

        logger.info(f"Document deleted (flushed): id={doc_id}")
        return True

    async def count_by_tenant(
        self,
        tenant_id: int,
        status: str | None = None,
        collection_id: int | None = None,
        abac_filter=None,
    ) -> int:
        """Count documents for a tenant.

        Args:
            tenant_id: Tenant ID
            status: Optional status filter

        Returns:
            Document count
        """
        query = select(Document).where(Document.tenant_id == tenant_id)

        if status:
            query = query.where(Document.status == status)

        if collection_id is not None:
            query = query.where(Document.collection_id == collection_id)

        if abac_filter is not None:
            query = query.where(abac_filter)

        result = await self.db.execute(query)
        return len(list(result.scalars().all()))

    async def get_document_stats(self, tenant_id: int, status: str | None = None) -> tuple[int, int]:
        """Get document count and total size for a tenant.

        Args:
            tenant_id: Tenant ID
            status: Optional status filter

        Returns:
            Tuple of (document_count, total_size_bytes)
        """
        stmt = select(
            func.count(Document.id),
            func.coalesce(func.sum(Document.file_size), 0),
        ).where(Document.tenant_id == tenant_id)

        if status:
            stmt = stmt.where(Document.status == status)

        result = await self.db.execute(stmt)
        row = result.one()
        return int(row[0] or 0), int(row[1] or 0)

    async def count_by_tenant_with_query(
        self,
        tenant_id: int,
        query: str,
        collection_id: int | None = None,
        abac_filter=None,
    ) -> int:
        """Count documents for a tenant with key-based filter.

        Args:
            tenant_id: Tenant ID
            query: Search query (ILIKE-based substring match)

        Returns:
            Document count
        """
        stmt = select(func.count()).select_from(Document).where(Document.tenant_id == tenant_id)

        if collection_id is not None:
            stmt = stmt.where(Document.collection_id == collection_id)

        normalized_query = query.strip()
        if normalized_query:
            pattern = f"%{normalized_query}%"
            stmt = stmt.where(Document.filename.ilike(pattern))

        if abac_filter is not None:
            stmt = stmt.where(abac_filter)
        result = await self.db.execute(stmt)
        return int(result.scalar_one() or 0)

    async def list_pending_parse(self, tenant_id: int, *, limit: int = 10) -> list[Document]:
        """Documents awaiting background parse (not yet submitted to async parser)."""
        stmt = (
            select(Document)
            .join(
                ResourceIndex,
                (ResourceIndex.resource_id == Document.id)
                & (ResourceIndex.tenant_id == Document.tenant_id)
                & (ResourceIndex.resource_type == RESOURCE_TYPE_DOCUMENT),
            )
            .where(
                Document.tenant_id == tenant_id,
                Document.status == DocumentStatus.PROCESSING.value,
                ResourceIndex.parsed_at.is_(None),
                ResourceIndex.parse_job_id.is_(None),
                ResourceIndex.parse_error_at.is_(None),
            )
            .order_by(Document.upload_date.asc())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def list_ids_by_collection(self, tenant_id: int, collection_id: int) -> list[int]:
        stmt = select(Document.id).where(
            Document.tenant_id == tenant_id,
            Document.collection_id == collection_id,
        )
        result = await self.db.execute(stmt)
        return [row[0] for row in result.all()]

    async def list_parse_target_ids(
        self,
        tenant_id: int,
        *,
        document_id: int | None = None,
        collection_id: int | None = None,
        failed_only: bool = False,
    ) -> list[int]:
        if document_id is not None:
            document_db = await self.get_by_id_and_tenant(document_id, tenant_id)
            if document_db is None:
                raise ValueError(f"Document not found: {document_id}")
            return [document_id]

        statuses = (
            [DocumentStatus.FAILED.value]
            if failed_only
            else [DocumentStatus.PROCESSING.value, DocumentStatus.FAILED.value]
        )
        stmt = select(Document.id).where(Document.tenant_id == tenant_id, Document.status.in_(statuses))
        if collection_id is not None:
            stmt = stmt.where(Document.collection_id == collection_id)
        result = await self.db.execute(stmt)
        return [row[0] for row in result.all()]

    async def count_statuses(self, tenant_id: int) -> list[tuple[str, int]]:
        stmt = (
            select(Document.status, func.count(Document.id))
            .where(Document.tenant_id == tenant_id)
            .group_by(Document.status)
        )
        result = await self.db.execute(stmt)
        return [(row[0], row[1]) for row in result.all()]

    async def list_parse_issues(self, tenant_id: int, *, limit: int = 20) -> list[ParseIssueRow]:
        from apps.shared.search.domain import VectorStatus

        stmt = (
            select(
                Document.id,
                Document.filename,
                Document.status,
                ResourceIndex.parse_job_id,
                ResourceIndex.parsed_at,
                ResourceIndex.parse_error,
                ResourceIndex.vector_status,
            )
            .join(
                ResourceIndex,
                (ResourceIndex.resource_id == Document.id)
                & (ResourceIndex.resource_type == RESOURCE_TYPE_DOCUMENT)
                & (ResourceIndex.tenant_id == Document.tenant_id),
            )
            .where(
                or_(
                    Document.status.in_([DocumentStatus.PROCESSING.value, DocumentStatus.FAILED.value]),
                    ResourceIndex.parse_error.isnot(None),
                    (
                        ResourceIndex.parse_job_id.isnot(None)
                        & ResourceIndex.parsed_at.is_(None)
                        & ResourceIndex.parse_error_at.is_(None)
                    ),
                    ResourceIndex.vector_status.in_([VectorStatus.FAILED, VectorStatus.PERMANENT_FAILED]),
                )
            )
            .where(Document.tenant_id == tenant_id)
            .order_by(Document.updated_at.desc())
            .limit(limit)
        )
        rows = (await self.db.execute(stmt)).all()
        return [
            {
                "document_id": row[0],
                "filename": row[1],
                "status": row[2],
                "parse_job_id": row[3],
                "parsed_at": row[4],
                "parse_error": row[5],
                "vector_status": row[6],
            }
            for row in rows
        ]


class DocumentCollectionRepository(BaseRepository[DocumentCollection]):
    def __init__(self, db: AsyncSession):
        super().__init__(DocumentCollection, db)

    async def get_by_id_and_tenant(self, collection_id: int, tenant_id: int) -> DocumentCollection | None:
        result = await self.db.execute(
            select(DocumentCollection)
            .options(selectinload(DocumentCollection.owner_user))
            .where(DocumentCollection.id == collection_id, DocumentCollection.tenant_id == tenant_id)
        )
        return result.scalar_one_or_none()

    async def get_by_tenant_and_name(self, tenant_id: int, name: str) -> DocumentCollection | None:
        result = await self.db.execute(
            select(DocumentCollection).where(
                DocumentCollection.tenant_id == tenant_id,
                DocumentCollection.name == name,
            )
        )
        return result.scalar_one_or_none()

    async def list_by_tenant(
        self,
        tenant_id: int,
        *,
        scope_clause: ColumnElement[bool] | None = None,
    ) -> list[DocumentCollection]:
        stmt = (
            select(DocumentCollection)
            .options(selectinload(DocumentCollection.owner_user))
            .where(DocumentCollection.tenant_id == tenant_id)
            .order_by(DocumentCollection.name)
        )
        if scope_clause is not None:
            stmt = stmt.where(scope_clause)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def count_documents_by_collection(self, tenant_id: int, collection_ids: list[int]) -> dict[int, int]:
        if not collection_ids:
            return {}
        stmt = (
            select(Document.collection_id, func.count(Document.id))
            .where(
                Document.tenant_id == tenant_id,
                Document.collection_id.in_(collection_ids),
                Document.status.in_(_ACTIVE_STATUSES),
            )
            .group_by(Document.collection_id)
        )
        result = await self.db.execute(stmt)
        return {row[0]: int(row[1]) for row in result.all()}

    async def create(self, domain: DocumentCollectionDomain) -> DocumentCollection:
        record = domain_collection_to_db_model(domain)
        self.db.add(record)
        await self.db.flush()
        await self.db.refresh(record)
        return record

    async def update_fields(
        self,
        collection_id: int,
        tenant_id: int,
        *,
        name: str | None = None,
        description: str | None = None,
    ) -> DocumentCollection | None:
        record = await self.get_by_id_and_tenant(collection_id, tenant_id)
        if record is None:
            return None
        if name is not None:
            record.name = name
        if description is not None:
            record.description = description
        await self.db.flush()
        await self.db.refresh(record)
        return record

    async def delete(self, collection_id: int, tenant_id: int) -> bool:
        record = await self.get_by_id_and_tenant(collection_id, tenant_id)
        if record is None:
            return False
        await self.db.delete(record)
        await self.db.flush()
        return True

    async def count_documents_in_collection(self, collection_id: int, tenant_id: int) -> int:
        stmt = (
            select(func.count())
            .select_from(Document)
            .where(
                Document.tenant_id == tenant_id,
                Document.collection_id == collection_id,
                Document.status.in_(["processing", "active"]),
            )
        )
        result = await self.db.execute(stmt)
        return int(result.scalar_one() or 0)
