"""Search — catalog sync (publish) and hybrid retrieval (query).

- :mod:`sync_service` — ``ResourceIndex`` CRUD and publish to FTS + Chroma
- :mod:`retrieval_service` — hybrid search for documents, assets, API operations
- :mod:`publish` — build lexical text and chunks from ``raw_content``
"""

from apps.shared.search.repository import ResourceIndexRepository
from apps.shared.search.retrieval_service import SearchService
from apps.shared.search.sync_service import ResourceIndexService

SearchSyncService = ResourceIndexService

__all__ = [
    "ResourceIndexRepository",
    "ResourceIndexService",
    "SearchService",
    "SearchSyncService",
]