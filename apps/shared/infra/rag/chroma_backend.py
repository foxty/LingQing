"""Chroma backend implementations for the vector backend contract.

This is an infrastructure layer that only handles vector storage operations.
Embedding configuration is handled by the service layer (RAGManager callers).
"""

import asyncio
from typing import Any

import chromadb
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings

from apps.config import EnvConfig
from apps.shared.infra.rag.backend import MetadataFilter, VectorGetResult, VectorRecord, VectorStoreBackend


class BaseChromaBackend(VectorStoreBackend):
    """Shared behavior for Chroma backends."""

    # Max documents per embedding API call. DashScope-compatible APIs limit batch to 10.
    EMBEDDING_BATCH_SIZE = 10

    def __init__(self, tenant_id: int, embeddings: Embeddings | None = None):
        self.tenant_id = tenant_id
        self.embeddings = embeddings
        self.collection_name = f"{EnvConfig.CHROMA_COLLECTION_PREFIX}{tenant_id}"
        from apps.shared.utils.logger import get_logger

        self._logger = get_logger(__name__)
        if embeddings:
            self._logger.info(
                "ChromaBackend: initialized with custom embeddings for tenant_id=%s, collection=%s",
                tenant_id,
                self.collection_name,
            )
        else:
            self._logger.info(
                "ChromaBackend: initialized with default embeddings for tenant_id=%s, collection=%s",
                tenant_id,
                self.collection_name,
            )
        self._vectorstore: Chroma | None = None

    def _build_common_kwargs(self) -> dict[str, Any]:
        kwargs: dict[str, Any] = {}
        if self.embeddings:
            kwargs["embedding_function"] = self.embeddings
        return kwargs

    def _create_vectorstore(self) -> Chroma:
        raise NotImplementedError()

    def _ensure_vectorstore(self) -> Chroma:
        """Create the Chroma client on first vector operation.

        chromadb.HttpClient heartbeats with httpx timeout=None, so constructing
        it in __init__ can hang unit tests (and startup) when the server is down.
        """
        if self._vectorstore is None:
            self._vectorstore = self._create_vectorstore()
        return self._vectorstore

    async def add_records(self, records: list[VectorRecord]) -> None:
        documents = [
            Document(
                page_content=record["content"],
                metadata=record.get("metadata", {}),
            )
            for record in records
        ]
        vectorstore = self._ensure_vectorstore()
        # Batch to avoid embedding API batch size limits (e.g., DashScope max 10)
        batch_size = self.EMBEDDING_BATCH_SIZE
        for i in range(0, len(documents), batch_size):
            batch = documents[i : i + batch_size]
            await vectorstore.aadd_documents(batch)
            self._logger.debug(
                "Added batch %d/%d (%d docs) for tenant_id=%s",
                i // batch_size + 1,
                (len(documents) + batch_size - 1) // batch_size,
                len(batch),
                self.tenant_id,
            )

    async def similarity_search(
        self,
        query: str,
        k: int,
        filter_dict: MetadataFilter | None = None,
    ) -> list[VectorRecord]:
        vectorstore = self._ensure_vectorstore()
        if filter_dict is None:
            docs = await vectorstore.asimilarity_search(query, k=k)
        else:
            docs = await vectorstore.asimilarity_search(query, k=k, filter=filter_dict)

        return [
            {
                "content": doc.page_content,
                "metadata": doc.metadata or {},
            }
            for doc in docs
        ]

    async def get(
        self,
        where: MetadataFilter,
        limit: int | None = None,
        include: list[str] | None = None,
    ) -> VectorGetResult:
        kwargs: dict[str, Any] = {"where": where}
        if limit is not None:
            kwargs["limit"] = limit
        if include is not None:
            kwargs["include"] = include
        raw_results = await asyncio.to_thread(self._ensure_vectorstore().get, **kwargs)

        ids = raw_results.get("ids") or []
        documents = raw_results.get("documents") or []
        metadatas = raw_results.get("metadatas") or [{} for _ in documents]

        if not documents and metadatas:
            documents = ["" for _ in metadatas]

        records = [
            {
                "content": content,
                "metadata": metadata or {},
            }
            for content, metadata in zip(documents, metadatas)
        ]
        return {
            "ids": ids,
            "records": records,
        }

    async def delete(
        self,
        where: MetadataFilter | None = None,
        ids: list[str] | None = None,
    ) -> None:
        vectorstore = self._ensure_vectorstore()
        if ids is not None:
            await vectorstore.adelete(ids=ids)
            return
        if where is not None:
            await asyncio.to_thread(vectorstore.delete, where=where)
            return
        raise ValueError("Either where or ids must be provided to delete vectors")

    async def delete_collection(self) -> None:
        """Delete the entire collection.

        Used when embedding model changes to avoid dimension mismatch.
        The collection will be recreated on next write operation.
        """
        self._logger.warning(
            "Deleting entire collection for tenant_id=%s, collection_name=%s",
            self.tenant_id,
            self.collection_name,
        )
        client = self._ensure_vectorstore()._client
        await asyncio.to_thread(client.delete_collection, name=self.collection_name)
        self._vectorstore = None
        self._logger.info(
            "Collection deleted for tenant_id=%s, collection_name=%s",
            self.tenant_id,
            self.collection_name,
        )


class HttpChromaBackend(BaseChromaBackend):
    """Client/server Chroma backend using HttpClient."""

    def _create_vectorstore(self) -> Chroma:
        kwargs = self._build_common_kwargs()
        client_settings = chromadb.config.Settings(anonymized_telemetry=False)
        kwargs["client"] = chromadb.HttpClient(
            **EnvConfig.chroma_http_client_kwargs(),
            settings=client_settings,
        )
        kwargs["collection_name"] = self.collection_name
        return Chroma(**kwargs)

    def describe(self) -> dict[str, Any]:
        return {
            "backend": "chroma-http",
            "tenant_id": self.tenant_id,
            "url": EnvConfig.CHROMA_URL,
            "collection_name": self.collection_name,
        }


def get_vector_backend(
    tenant_id: int,
    embeddings: Embeddings | None = None,
) -> VectorStoreBackend:
    """Factory for vector backend implementations.

    Args:
        tenant_id: Tenant identifier
        embeddings: Pre-created embeddings instance. If None, uses Chroma's default.

    Returns:
        VectorStoreBackend instance
    """
    return HttpChromaBackend(tenant_id=tenant_id, embeddings=embeddings)
