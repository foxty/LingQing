"""RAG Manager for document storage and retrieval using vector databases.

This module provides a class-based RAG manager following SOLID principles:
- Single Responsibility: Separated concerns for loading, processing, and storage
- Open/Closed: Extensible through inheritance and composition
- Liskov Substitution: Base classes can be substituted with implementations
- Interface Segregation: Clean, focused interfaces
- Dependency Inversion: Depends on abstractions (base classes)

Multi-Tenancy Support:
    Each tenant has isolated vector storage. Documents are tracked by:
    - tenant_id: Unique tenant identifier
    - doc_id: Unique document identifier (UUID)
    - doc_url: Document source location (file path)

Example Usage:
    # Create a RAG manager instance for a tenant
    from apps.shared.infra.rag import RAGManager

    manager = RAGManager(tenant_id="company_123")

    # Add new documents (returns chunk count)
    chunk_count = manager.add_documents(
        doc_path="path/to/new_doc.pdf",
        doc_id=123,
        filename="new_doc.pdf"
    )


    # Retrieve relevant documents
    results = manager.retrieve("What are the company goals?", k=5)

    # Get statistics
    stats = manager.get_stats()

Note:
    For batch document uploads, use DocumentService API instead of
    directly calling RAGManager to ensure metadata consistency.
"""

from typing import List

from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

from apps.shared.infra.rag.backend import VectorRecord, VectorStoreBackend
from apps.shared.infra.rag.chroma_backend import get_vector_backend
from apps.shared.utils.logger import get_logger

# Initialize logger
logger = get_logger(__name__)

# Default configuration
DEFAULT_CHUNK_SIZE = 512
DEFAULT_CHUNK_OVERLAP = 64


class RAGManager:
    """Main RAG Manager class for document management and retrieval.

    This class follows SOLID principles:
    - SRP: Focused on managing the RAG lifecycle
    - OCP: Extensible through composition (loader, processor can be swapped)
    - LSP: Can be subclassed for specialized behavior
    - ISP: Clean interface with focused methods
    - DIP: Depends on abstractions (DocumentLoader, TextSplitter)

    Multi-Tenancy:
    - Each tenant has isolated vector storage semantics
    - Documents are filtered by tenant_id
    - Physical storage is delegated to vector backend implementations

    Embedding Configuration:
    - Supports configurable embedding models via tenant settings
    - Falls back to Chroma's built-in embedding when no config is provided
    """

    def __init__(
        self,
        tenant_id: int,
        embeddings: Embeddings | None = None,
    ):
        """Initialize RAG Manager.

        Args:
            tenant_id: Unique identifier for the tenant (required).
            embeddings: Pre-created Embeddings instance. If None, uses Chroma's default.
            text_splitter: Text splitter instance. If None, uses default.
        """
        self.tenant_id = tenant_id
        self.embeddings = embeddings
        self._text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=DEFAULT_CHUNK_SIZE,
            chunk_overlap=DEFAULT_CHUNK_OVERLAP,
            separators=["\n\n", "\n", "。", "？", "！", " ", ""],
        )

        # Adapter is cheap; the HTTP client is created on first vector operation.
        self._backend: VectorStoreBackend = get_vector_backend(
            tenant_id=tenant_id,
            embeddings=embeddings,
        )
        backend_info = self._backend.describe()
        logger.debug("RAGManager initialized for tenant '%s' with backend=%s", tenant_id, backend_info)

    def _split_documents(self, documents: List[Document]) -> List[Document]:
        """Split documents into chunks.

        Args:
            documents: List of documents to split.

        Returns:
            List of document chunks.
        """
        if not documents:
            return []

        split_docs = self._text_splitter.split_documents(documents)
        logger.debug(f"Split {len(documents)} documents into {len(split_docs)} chunks")
        return split_docs

    def split_documents(self, documents: List[Document]) -> List[Document]:
        """Public wrapper for splitting documents into chunks.

        Args:
            documents: List of documents to split.

        Returns:
            List of document chunks.
        """
        return self._split_documents(documents)

    def _add_documents_to_vectorstore(self, documents: List[Document]) -> None:
        """Add documents to the existing vector store.

        Args:
            documents: List of documents to add
        """
        # Kept for backward compatibility. Prefer add_chunks() async path.
        raw_vectorstore = getattr(self._backend, "_vectorstore", None)
        if raw_vectorstore is None:
            raise RuntimeError("Sync add_documents path is unavailable for this backend")
        raw_vectorstore.add_documents(documents)
        logger.debug(f"Added {len(documents)} documents to vector backend")

    async def add_chunks(self, chunks: List[Document]) -> int:
        """Add pre-processed chunks to vector store.

        This is a pure vector store operation - chunks should be fully prepared
        with all metadata before calling this method.

        Args:
            chunks: Fully prepared LangChain Documents with complete metadata

        Returns:
            Number of chunks added

        Note:
            Chunks must already have source_type, resource_type, resource_id, and tenant_id
            in their metadata. Use ResourceIndexService to prepare chunks.
        """
        if not chunks:
            logger.warning("No chunks to add")
            return 0

        records: list[VectorRecord] = [
            {
                "content": chunk.page_content,
                "metadata": chunk.metadata or {},
            }
            for chunk in chunks
        ]
        await self._backend.add_records(records)
        return len(chunks)

    async def remove_by_resource(self, resource_type: str, resource_id: int) -> bool:
        """Remove all chunks for a specific resource.

        Uses resource_type + resource_id metadata fields.

        Args:
            resource_type: Resource type (e.g., "document", "asset", "api_connector")
            resource_id: Internal DB resource ID

        Returns:
            True if successful, False otherwise
        """
        logger.debug(
            f"Removing chunks for resource_type={resource_type}, resource_id={resource_id} "
            f"for tenant '{self.tenant_id}'"
        )

        try:
            where_filter = {
                "$and": [
                    {"tenant_id": self.tenant_id},
                    {"resource_type": resource_type},
                    {"resource_id": resource_id},
                ]
            }

            await self._backend.delete(where=where_filter)
            logger.debug(f"Delete requested for resource_type={resource_type}, resource_id={resource_id}")
            return True
        except Exception as e:
            logger.error(f"Error removing chunks: {e}", exc_info=True)
            return False

    async def retrieve(
        self,
        query: str,
        k: int = 5,
        resource_types: List[str] | None = None,
    ) -> List[Document]:
        """Retrieve relevant documents with optional filtering by source type.

        Supports unified retrieval across different content types (documents, assets)
        with optional filtering by source type.

        Args:
            query: Query string
            k: Number of documents to retrieve
            source_types: Optional filter by source type
                         (e.g., [RAGSourceType.DOCUMENT.value, RAGSourceType.ASSET.value])
                         If None, retrieves all types

        Returns:
            List of relevant documents with metadata
        """
        logger.debug(
            f"Retrieving for tenant '{self.tenant_id}', query: {query[:50]}..., source_types: {resource_types}"
        )

        # Always scope retrieval by tenant and add optional source filters.
        # Use equality for single source_type to avoid brittle query-plan behavior in some Chroma versions.
        conditions: list[dict] = [{"tenant_id": self.tenant_id}]
        if resource_types:
            if len(resource_types) == 1:
                conditions.append({"resource_type": resource_types[0]})
            else:
                conditions.append({"resource_type": {"$in": resource_types}})

        filter_dict = {"$and": conditions} if len(conditions) > 1 else conditions[0]

        result_records = await self._backend.similarity_search(query=query, k=k, filter_dict=filter_dict)

        docs = [
            Document(
                page_content=record["content"],
                metadata=record.get("metadata", {}),
            )
            for record in result_records
        ]

        logger.debug(f"Retrieved {len(docs)} documents for tenant '{self.tenant_id}'")
        return docs

    async def clear_by_source_type(self, source_type: str) -> int:
        """Clear all vectors for a specific source type.

        ⚠️ WARNING: This is a destructive operation used for full sync rebuild!

        Args:
            source_type: Source type to clear (e.g., RAGSourceType.DOCUMENT.value)

        Returns:
            Number of chunks deleted

        Raises:
            Exception: If deletion fails
        """
        logger.warning(f"⚠️  Clearing all vectors for source_type='{source_type}', tenant_id={self.tenant_id}")

        try:
            # Get all IDs for this source type
            results = await self._backend.get(
                where={"$and": [{"tenant_id": self.tenant_id}, {"source_type": source_type}]},
                include=["metadatas"],  # Only need IDs
            )

            if not results or not results.get("ids"):
                logger.info(f"No vectors found for source_type '{source_type}'")
                return 0

            # Delete all matching IDs
            ids_to_delete = results["ids"]
            await self._backend.delete(ids=ids_to_delete)

            logger.info(
                f"Cleared {len(ids_to_delete)} vectors for source_type='{source_type}', tenant_id={self.tenant_id}"
            )
            return len(ids_to_delete)

        except Exception as e:
            logger.error(f"Failed to clear vectors for source_type '{source_type}': {e}", exc_info=True)
            raise

    async def clear_collection(self) -> None:
        """Delete the entire vector collection for this tenant.

        ⚠️ WARNING: This is a destructive operation!

        Used when embedding model changes to avoid dimension mismatch.
        The collection will be recreated on next write operation with the new embedding model.

        This should be called before marking resources as stale for re-indexing.
        """
        logger.warning(
            "⚠️  Deleting entire vector collection for tenant_id=%s",
            self.tenant_id,
        )
        await self._backend.delete_collection()
        logger.info(
            "Vector collection deleted for tenant_id=%s, will be recreated on next indexing",
            self.tenant_id,
        )

    async def get_resource_ids_by_type(self, resource_type: str) -> set[int]:
        """Get all unique resource_ids for a given resource_type and tenant.

        Used for orphan detection by comparing vector store IDs against DB IDs.

        Args:
            resource_type: Resource type (e.g., 'document', 'asset', 'api_connector')

        Returns:
            Set of resource_ids
        """
        logger.info(f"Retrieving resource_ids for tenant='{self.tenant_id}', type='{resource_type}'")

        try:
            results = await self._backend.get(
                where={
                    "$and": [
                        {"tenant_id": self.tenant_id},
                        {"resource_type": resource_type},
                    ]
                },
                limit=10000,
                include=["metadatas"],
            )

            if not results or not results.get("records"):
                return set()

            resource_ids = {
                record.get("metadata", {}).get("resource_id")
                for record in results["records"]
                if isinstance(record.get("metadata", {}).get("resource_id"), int)
            }

            logger.info(
                f"Found {len(resource_ids)} unique resource_ids for tenant='{self.tenant_id}', type='{resource_type}'"
            )
            return resource_ids

        except Exception as e:
            logger.error(f"Error retrieving resource_ids: {e}", exc_info=True)
            return set()

    async def delete_by_resource_type(self, resource_type: str, resource_ids: set[int]) -> int:
        """Delete vectors for specific resource_ids within a resource_type.

        Used for orphan cleanup.

        Args:
            resource_type: Resource type filter
            resource_ids: Set of resource_ids to delete

        Returns:
            Number of chunks deleted
        """
        if not resource_ids:
            return 0

        logger.warning(f"Deleting {len(resource_ids)} orphaned resource_ids for type='{resource_type}'")

        try:
            # Delete in batches to avoid large where clauses
            deleted = 0
            resource_id_list = list(resource_ids)
            batch_size = 100
            for i in range(0, len(resource_id_list), batch_size):
                batch = resource_id_list[i : i + batch_size]
                results = await self._backend.get(
                    where={
                        "$and": [
                            {"tenant_id": self.tenant_id},
                            {"resource_type": resource_type},
                            {"resource_id": {"$in": batch}},
                        ]
                    },
                    include=["ids"],
                )
                if results and results.get("ids"):
                    await self._backend.delete(ids=results["ids"])
                    deleted += len(results["ids"])

            logger.info(f"Deleted {deleted} orphaned chunks for type='{resource_type}'")
            return deleted

        except Exception as e:
            logger.error(f"Failed to delete orphaned vectors: {e}", exc_info=True)
            raise

    async def get_chunks_by_resource(
        self,
        *,
        resource_type: str,
        resource_id: int,
        limit: int = 100,
    ) -> List[Document]:
        """Retrieve all chunks for a given resource type and ID.

        Uses resource_type + resource_id metadata fields.

        Args:
            resource_type: Resource type (e.g., "document", "asset", "api_connector")
            resource_id: Internal DB resource ID
            limit: Maximum number of chunks to retrieve

        Returns:
            List of Document objects sorted by chunk_index
        """
        logger.debug(
            f"Retrieving chunks by resource: resource_type={resource_type}, "
            f"resource_id={resource_id}, limit={limit} (tenant: {self.tenant_id})"
        )

        try:
            results = await self._backend.get(
                where={
                    "$and": [
                        {"tenant_id": self.tenant_id},
                        {"resource_type": resource_type},
                        {"resource_id": resource_id},
                    ]
                },
                limit=limit,
            )

            if not results or not results.get("records"):
                return []

            documents = []
            for record in results["records"]:
                content = record["content"]
                metadata = record.get("metadata", {})
                documents.append(Document(page_content=content, metadata=metadata))

            documents.sort(key=lambda x: x.metadata.get("chunk_index", 0))
            return documents

        except Exception as e:
            logger.error(f"Error retrieving chunks by resource: {e}", exc_info=True)
            return []

    async def get_context_chunks_by_resource(
        self,
        *,
        resource_type: str,
        resource_id: int,
        chunk_index: int,
        context_range: int,
    ) -> List[Document]:
        """Retrieve contextual chunks around a specific chunk by resource type and ID.

        Uses resource_type + resource_id metadata fields directly.

        Args:
            resource_type: Resource type (e.g., "document", "asset", "api_connector")
            resource_id: Internal DB resource ID
            chunk_index: Target chunk index
            context_range: Number of chunks to retrieve before and after

        Returns:
            List of Document objects sorted by chunk_index
        """
        logger.info(
            f"Retrieving context chunks by resource: resource_type={resource_type}, "
            f"resource_id={resource_id}, chunk_index={chunk_index}, range=±{context_range} (tenant: {self.tenant_id})"
        )

        try:
            start_idx = max(0, chunk_index - context_range)
            end_idx = chunk_index + context_range + 1

            results = await self._backend.get(
                where={
                    "$and": [
                        {"tenant_id": self.tenant_id},
                        {"resource_type": resource_type},
                        {"resource_id": resource_id},
                        {"chunk_index": {"$gte": start_idx}},
                        {"chunk_index": {"$lte": end_idx - 1}},
                    ]
                },
                limit=end_idx - start_idx,
            )

            if not results or not results.get("records"):
                return []

            context_chunks = []
            for record in results["records"]:
                content = record["content"]
                metadata = record.get("metadata", {})
                context_chunks.append(Document(page_content=content, metadata=metadata))

            context_chunks.sort(key=lambda x: x.metadata.get("chunk_index", 0))
            return context_chunks

        except Exception as e:
            logger.error(f"Error retrieving context chunks by resource: {e}", exc_info=True)
            return []

    async def get_chunks_by_page(
        self,
        *,
        resource_type: str,
        resource_id: int,
        page: int,
        limit: int = 200,
    ) -> List[Document]:
        """Retrieve all chunks on one page for a resource."""
        logger.debug(
            "Retrieving page chunks: resource_type=%s resource_id=%s page=%s tenant=%s",
            resource_type,
            resource_id,
            page,
            self.tenant_id,
        )
        try:
            results = await self._backend.get(
                where={
                    "$and": [
                        {"tenant_id": self.tenant_id},
                        {"resource_type": resource_type},
                        {"resource_id": resource_id},
                        {"page": page},
                    ]
                },
                limit=limit,
            )
            if not results or not results.get("records"):
                return []
            documents = [
                Document(page_content=record["content"], metadata=record.get("metadata", {}))
                for record in results["records"]
            ]
            documents.sort(key=lambda doc: doc.metadata.get("chunk_index", 0))
            return documents
        except Exception as e:
            logger.error("Error retrieving page chunks: %s", e, exc_info=True)
            return []

    async def get_stats(self) -> dict:
        """Get statistics about the vector store for this tenant.

        Note: For user-facing statistics (document counts, file sizes),
        use DocumentRepository.get_stats() or DocumentService.get_stats().

        Returns:
            Dictionary with vector store status.
        """
        try:
            # Verify vectorstore is accessible
            await self._backend.get(
                where={"tenant_id": self.tenant_id},
                limit=1,
            )

            return {
                "status": "active",
                "tenant_id": self.tenant_id,
            }
        except Exception as e:
            logger.error(f"Error getting stats: {e}", exc_info=True)
            return {"status": "error", "tenant_id": self.tenant_id, "error": str(e)}
