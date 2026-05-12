"""Document module (collections + documents)."""

from apps.shared.document.domain import DocumentCollectionDomain, DocumentDomain
from apps.shared.document.repository import DBDocumentRepository, DocumentCollectionRepository
from apps.shared.document.schemas import DocumentCollectionResponse, DocumentInfo

__all__ = [
    "DBDocumentRepository",
    "DocumentAccessScope",
    "DocumentCollectionDomain",
    "DocumentCollectionRepository",
    "DocumentCollectionResponse",
    "DocumentCollectionService",
    "DocumentDomain",
    "DocumentInfo",
    "DocumentService",
]


def __getattr__(name: str):
    if name == "DocumentService":
        from apps.shared.document.service import DocumentService

        return DocumentService
    if name == "DocumentAccessScope":
        from apps.shared.document.collection_service import DocumentAccessScope

        return DocumentAccessScope
    if name == "DocumentCollectionService":
        from apps.shared.document.collection_service import DocumentCollectionService

        return DocumentCollectionService
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
