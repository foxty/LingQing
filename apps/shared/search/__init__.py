"""Search module — resource indexing (write path) and hybrid search (read path)."""

from apps.shared.search.repository import ResourceIndexRepository
from apps.shared.search.search_service import SearchService


# Lazy import to avoid circular dependency with data_source module
def __getattr__(name: str):
    if name in {"ResourceIndexService", "SearchIndexService"}:
        from apps.shared.search.indexing_service import ResourceIndexService

        return ResourceIndexService
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["ResourceIndexRepository", "ResourceIndexService", "SearchService"]
