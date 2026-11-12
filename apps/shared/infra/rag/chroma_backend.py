"""Chroma backend implementations for the vector backend contract.

This is an infrastructure layer that only handles vector storage operations.
Embedding configuration is required from the service layer (tenant default embedding profile).
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable, Coroutine
from typing import Any, TypeVar

import chromadb
import httpx
from chromadb.api import ClientAPI
from chromadb.api.models.Collection import Collection
from langchain_core.embeddings import Embeddings

from apps.config import EnvConfig
from apps.shared.core.exceptions import ValidationError
from apps.shared.infra.rag.backend import MetadataFilter, VectorGetResult, VectorRecord, VectorStoreBackend
from apps.shared.infra.rag.chroma_embedding import LangChainEmbeddingFunction

_T = TypeVar("_T")


def _chroma_http_timeout_seconds() -> float:
    return float(EnvConfig.CHROMA_HTTP_TIMEOUT_SECONDS)


def _apply_chroma_http_client_timeout(client: ClientAPI) -> None:
    """Patch chromadb FastAPI client's httpx session (upstream default is timeout=None)."""
    timeout = _chroma_http_timeout_seconds()
    if timeout <= 0:
        return
    server = getattr(client, "_server", None)
    session = getattr(server, "_session", None)
    if session is not None:
        session.timeout = httpx.Timeout(timeout)


def _sanitize_metadata(metadata: dict[str, Any]) -> dict[str, str | int | float | bool]:
    """Chroma accepts only primitive metadata values."""
    sanitized: dict[str, str | int | float | bool] = {}
    for key, value in metadata.items():
        if value is None:
            continue
        if isinstance(value, (str, int, float, bool)):
            sanitized[key] = value
        else:
            sanitized[key] = str(value)
    return sanitized


class HttpChromaBackend(VectorStoreBackend):
    """Chroma vector store over HTTP (chromadb.HttpClient)."""

    # Max documents per embedding API call. DashScope-compatible APIs limit batch to 10.
    EMBEDDING_BATCH_SIZE = 10

    def __init__(self, tenant_id: int, embeddings: Embeddings):
        if embeddings is None:
            raise ValidationError("Default embedding model profile is not configured")
        self.tenant_id = tenant_id
        self.embeddings = embeddings
        self.collection_name = f"{EnvConfig.CHROMA_COLLECTION_PREFIX}{tenant_id}"
        from apps.shared.utils.logger import get_logger

        self._logger = get_logger(__name__)
        self._logger.info(
            "ChromaBackend: initialized for tenant_id=%s, collection=%s",
            tenant_id,
            self.collection_name,
        )
        self._client: ClientAPI | None = None
        self._collection: Collection | None = None
        self._collection_lock = asyncio.Lock()

    def _initialize_collection(self) -> Collection:
        """Create HttpClient and collection (blocking). Must run in a worker thread."""
        if self._collection is not None:
            return self._collection

        client_settings = chromadb.config.Settings(anonymized_telemetry=False)
        client = chromadb.HttpClient(
            **EnvConfig.chroma_http_client_kwargs(),
            settings=client_settings,
        )
        _apply_chroma_http_client_timeout(client)

        collection = client.get_or_create_collection(
            name=self.collection_name,
            embedding_function=LangChainEmbeddingFunction(self.embeddings),
        )
        self._client = client
        self._collection = collection
        return self._collection

    def _ensure_collection(self) -> Collection:
        """Synchronous accessor for tests and thread-pool callers."""
        return self._initialize_collection()

    async def _aget_collection(self) -> Collection:
        if self._collection is not None:
            return self._collection
        async with self._collection_lock:
            if self._collection is not None:
                return self._collection
            timeout = _chroma_http_timeout_seconds()
            if timeout > 0:
                return await asyncio.wait_for(
                    asyncio.to_thread(self._initialize_collection),
                    timeout=timeout,
                )
            return await asyncio.to_thread(self._initialize_collection)

    async def _await_with_chroma_timeout(self, coro: Coroutine[Any, Any, _T] | Awaitable[_T]) -> _T:
        timeout = _chroma_http_timeout_seconds()
        if timeout > 0:
            return await asyncio.wait_for(coro, timeout=timeout)
        return await coro

    async def _run_collection_op(self, fn: Callable[..., _T], *args: Any, **kwargs: Any) -> _T:
        await self._aget_collection()
        return await self._await_with_chroma_timeout(asyncio.to_thread(fn, *args, **kwargs))

    async def add_records(self, records: list[VectorRecord]) -> None:
        collection = await self._aget_collection()
        batch_size = self.EMBEDDING_BATCH_SIZE
        for i in range(0, len(records), batch_size):
            batch = records[i : i + batch_size]
            ids = [str(uuid.uuid4()) for _ in batch]
            documents = [record["content"] for record in batch]
            metadatas = [_sanitize_metadata(record.get("metadata", {})) for record in batch]
            await self._run_collection_op(
                collection.add,
                ids=ids,
                documents=documents,
                metadatas=metadatas,
            )
            self._logger.debug(
                "Added batch %d/%d (%d docs) for tenant_id=%s",
                i // batch_size + 1,
                (len(records) + batch_size - 1) // batch_size,
                len(batch),
                self.tenant_id,
            )

    async def similarity_search(
        self,
        query: str,
        k: int,
        filter_dict: MetadataFilter | None = None,
    ) -> list[VectorRecord]:
        collection = await self._aget_collection()
        query_kwargs: dict[str, Any] = {
            "query_texts": [query],
            "n_results": k,
            "include": ["documents", "metadatas"],
        }
        if filter_dict is not None:
            query_kwargs["where"] = filter_dict

        raw = await self._run_collection_op(collection.query, **query_kwargs)
        documents = (raw.get("documents") or [[]])[0]
        metadatas = (raw.get("metadatas") or [[]])[0]
        return [
            {
                "content": doc or "",
                "metadata": meta or {},
            }
            for doc, meta in zip(documents, metadatas)
        ]

    async def get(
        self,
        where: MetadataFilter,
        limit: int | None = None,
        include: list[str] | None = None,
    ) -> VectorGetResult:
        collection = await self._aget_collection()
        kwargs: dict[str, Any] = {"where": where}
        if limit is not None:
            kwargs["limit"] = limit
        if include is not None:
            chroma_include = [item for item in include if item != "ids"]
            if chroma_include:
                kwargs["include"] = chroma_include

        raw_results = await self._run_collection_op(collection.get, **kwargs)

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
        collection = await self._aget_collection()
        if ids is not None:
            await self._run_collection_op(collection.delete, ids=ids)
            return
        if where is not None:
            await self._run_collection_op(collection.delete, where=where)
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
        await self._aget_collection()
        client = self._client
        if client is None:
            raise RuntimeError("Chroma client not initialized")
        await self._await_with_chroma_timeout(
            asyncio.to_thread(client.delete_collection, name=self.collection_name)
        )
        self._client = None
        self._collection = None
        self._logger.info(
            "Collection deleted for tenant_id=%s, collection_name=%s",
            self.tenant_id,
            self.collection_name,
        )

    def describe(self) -> dict[str, Any]:
        return {
            "backend": "chroma-http",
            "tenant_id": self.tenant_id,
            "url": EnvConfig.CHROMA_URL,
            "collection_name": self.collection_name,
        }


def get_vector_backend(
    tenant_id: int,
    embeddings: Embeddings,
) -> VectorStoreBackend:
    """Factory for vector backend implementations.

    Args:
        tenant_id: Tenant identifier
        embeddings: Tenant-configured embedding client (required).

    Returns:
        VectorStoreBackend instance
    """
    return HttpChromaBackend(tenant_id=tenant_id, embeddings=embeddings)
