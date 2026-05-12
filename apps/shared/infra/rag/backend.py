"""Vector backend contracts for RAG manager.

This module defines the stable API boundary between RAGManager and concrete
vector store providers.
"""

from abc import ABC, abstractmethod
from typing import Any, TypedDict


class VectorRecord(TypedDict):
    """Provider-neutral vector payload exchanged with backends."""

    content: str
    metadata: dict[str, Any]


MetadataFilter = dict[str, Any]


class VectorGetResult(TypedDict):
    """Normalized backend get result."""

    ids: list[str]
    records: list[VectorRecord]


class VectorStoreBackend(ABC):
    """Contract between RAGManager and vector store implementations.

    All concrete backends must implement this interface so RAGManager can stay
    backend-agnostic.
    """

    @abstractmethod
    async def add_records(self, records: list[VectorRecord]) -> None:
        """Add vector records to vector store."""

    @abstractmethod
    async def similarity_search(
        self,
        query: str,
        k: int,
        filter_dict: MetadataFilter | None = None,
    ) -> list[VectorRecord]:
        """Run vector similarity search with optional metadata filtering."""

    @abstractmethod
    async def get(
        self,
        where: MetadataFilter,
        limit: int | None = None,
        include: list[str] | None = None,
    ) -> VectorGetResult:
        """Query vectors by metadata filters."""

    @abstractmethod
    async def delete(
        self,
        where: MetadataFilter | None = None,
        ids: list[str] | None = None,
    ) -> None:
        """Delete vectors by metadata filter or explicit IDs."""

    @abstractmethod
    async def delete_collection(self) -> None:
        """Delete the entire collection.

        Used when embedding model changes to avoid dimension mismatch.
        The collection will be recreated on next write operation.
        """

    @abstractmethod
    def describe(self) -> dict[str, Any]:
        """Return backend metadata for logging and debugging."""
