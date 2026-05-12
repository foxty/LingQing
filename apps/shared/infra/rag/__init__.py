"""RAG (Retrieval-Augmented Generation) infrastructure.

Provides vector storage and retrieval capabilities for documents and metadata.
"""

from .backend import VectorRecord, VectorStoreBackend
from .chroma_backend import get_vector_backend
from .rag_manager import RAGManager

__all__ = [
    "RAGManager",
    "VectorStoreBackend",
    "VectorRecord",
    "get_vector_backend",
]
