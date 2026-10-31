"""Document module (collections + documents)."""

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
    if name in {"DocumentDomain", "DocumentCollectionDomain"}:
        from apps.shared.document.domain import DocumentCollectionDomain, DocumentDomain

        return DocumentCollectionDomain if name == "DocumentCollectionDomain" else DocumentDomain
    if name == "DBDocumentRepository":
        from apps.shared.document.repository import DBDocumentRepository

        return DBDocumentRepository
    if name == "DocumentCollectionRepository":
        from apps.shared.document.repository import DocumentCollectionRepository

        return DocumentCollectionRepository
    if name in {"DocumentCollectionResponse", "DocumentInfo"}:
        from apps.shared.document.schemas import DocumentCollectionResponse, DocumentInfo

        return DocumentCollectionResponse if name == "DocumentCollectionResponse" else DocumentInfo
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
