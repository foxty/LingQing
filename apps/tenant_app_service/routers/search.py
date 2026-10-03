"""Search API routes."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.core.auth import get_current_user
from apps.shared.db.session import get_db
from apps.shared.schemas.user import UserDTO
from apps.shared.llm_providers.embedding_resolver import resolve_tenant_embeddings
from apps.shared.search import SearchService
from apps.shared.search.schemas import (
    SearchResponse,
    SearchTarget,
)

router = APIRouter(prefix="/search", tags=["search"])

MAX_SEARCH_PAGE = 5

_DEFAULT_PAGE_SIZE_BY_SOURCE = {
    SearchTarget.DOCUMENT: 5,
    SearchTarget.ASSET: 10,
    SearchTarget.API_CONNECTOR: 10,
}

_MAX_PAGE_SIZE_BY_SOURCE = {
    SearchTarget.DOCUMENT: 10,
    SearchTarget.ASSET: 20,
    SearchTarget.API_CONNECTOR: 20,
}

_ALLOWED_SOURCES = (
    SearchTarget.DOCUMENT,
    SearchTarget.ASSET,
    SearchTarget.API_CONNECTOR,
)


def _normalize_sources(sources: list[str] | None) -> list[str]:
    requested = sources or [SearchTarget.DOCUMENT, SearchTarget.ASSET, SearchTarget.API_CONNECTOR]
    normalized = [source.strip().lower() for source in requested if source and source.strip()]
    deduped = list(dict.fromkeys(normalized))

    invalid = [source for source in deduped if source not in _ALLOWED_SOURCES]
    if invalid:
        raise HTTPException(status_code=400, detail=f"Invalid sources: {invalid}")

    if not deduped:
        raise HTTPException(status_code=400, detail="sources must not be empty")

    return deduped


def _resolve_page_size(sources: list[str], page_size: int | None) -> int:
    """Resolve effective page size with per-source defaults and caps."""
    if len(sources) == 1:
        source = sources[0]
        default_size = _DEFAULT_PAGE_SIZE_BY_SOURCE.get(source, 10)
        max_size = _MAX_PAGE_SIZE_BY_SOURCE.get(source, 20)
    else:
        default_size = 10
        max_size = 20
    effective_size = page_size

    if effective_size is None:
        effective_size = default_size

    if effective_size > max_size:
        raise HTTPException(
            status_code=400,
            detail=(f"page_size exceeds max for sources {sources}: max={max_size}, got={effective_size}"),
        )

    return effective_size


@router.get(
    "",
    summary="Search the knowledge base — query documents, data assets, and API operations using hybrid search",
    response_model=SearchResponse,
)
async def search(
    query: str = Query(..., min_length=1, description="Search query"),
    sources: list[str] | None = Query(
        default=None,
        description="Search sources: document, asset, api_connector. Repeat query param for multiple values.",
    ),
    page: int = Query(1, ge=1, le=MAX_SEARCH_PAGE, description="Page number (1-indexed)"),
    page_size: int | None = Query(None, ge=1, le=50, description="Results per page (resource-type capped)"),
    current_user: UserDTO = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Search the tenant knowledge base using hybrid semantic + keyword ranking (RRF).

    This is the primary API for knowledge retrieval. Use it to find relevant content
    before answering questions that may be covered by the tenant's uploaded materials.

    Searchable content types (controlled by `sources`):
    - **document** — uploaded files (PDFs, Word docs, spreadsheets, etc.) split into
      chunks and indexed in the vector DB. Results include a ranked snippet, chunk hints,
      and relevance scores. Agents should follow up with `retrieve_resource_context`
      using `chunk_indexes` from the search hints.
    - **asset** — data asset metadata (tables, views, datasets) including asset name,
      type, business description, column names/types, and row count. Useful for
      understanding what data is available and what a table/field means.
        - **api_connector** — API operation metadata (method/path/summary/tags) from
            API Connector definitions. Useful for finding callable upstream API actions.
        - To query multiple source types, pass repeated `sources` query params.

    Results are sorted by relevance score (descending). Each item includes:
    - `item_type`: "document", "asset", or "api_connector"
    - `title`: filename or asset name
    - `source_id`: document ID, asset ID, or operation UID
    - `snippet`: short preview of the most relevant content
    - `contents`: detailed content chunks (documents) or full metadata (assets)
    - `score`: relevance score from hybrid RRF ranking
    """
    normalized_sources = _normalize_sources(sources)
    effective_page_size = _resolve_page_size(normalized_sources, page_size)

    embeddings = await resolve_tenant_embeddings(current_user.tenant_id, db)
    service = SearchService(
        tenant_id=current_user.tenant_id,
        session=db,
        user_id=current_user.id,
        user_role=current_user.role,
        embeddings=embeddings,
    )
    items, pagination = await service.search_for_actor(
        query=query,
        sources=normalized_sources,
        page=page,
        page_size=effective_page_size,
    )

    return SearchResponse(
        items=items,
        total=pagination.total,
        page=pagination.page,
        page_size=pagination.page_size,
        total_pages=pagination.total_pages,
        has_next=pagination.page < min(pagination.total_pages, MAX_SEARCH_PAGE),
        has_prev=pagination.page > 1,
    )
