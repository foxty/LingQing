"""RAG tools for internal and external retrieval workflows.

Provides granular search tools for documents, assets, and API operations,
plus a unified context retrieval tool for expanding resource details.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, NamedTuple

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from apps.shared.core.exceptions import DomainException
from apps.shared.db.session import app_db_session
from apps.shared.domain.actor import ActorContext
from apps.shared.domain.types import (
    RESOURCE_TYPE_API_CONNECTOR,
    RESOURCE_TYPE_ASSET,
    RESOURCE_TYPE_DOCUMENT,
    SearchableResourceType,
)
from apps.shared.search import SearchService
from apps.shared.utils.logger import get_logger
from apps.shared.utils.pagination import PaginationRequest
from apps.tenant_app_service.agents.context import extract_runtime_context
from apps.tenant_app_service.agents.tools.tool_result import ToolResult

logger = get_logger(__name__)

MAX_SEARCH_PAGE = 5
DEFAULT_PAGE_SIZE = 10
MAX_PAGE_SIZE = 20
MAX_RETRIEVE_CHUNK_INDEXES = 10

SearchFn = Callable[[SearchService, str, int, int], Awaitable[tuple[list[Any], PaginationRequest]]]


class _SearchRuntime(NamedTuple):
    tenant_id: int
    user_id: int
    user_role: str
    tenant_config: dict | None
    collection_ids: list[int] | None
    data_source_ids: list[int] | None
    api_ids: list[int] | None
    delegate: bool


class SearchQueryInput(BaseModel):
    query: str = Field(..., min_length=1, description="Search query")
    page: int = Field(default=1, ge=1, le=MAX_SEARCH_PAGE)
    page_size: int = Field(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE)


SearchDocumentsInput = SearchQueryInput
SearchDataAssetsInput = SearchQueryInput
SearchApisInput = SearchQueryInput


class RetrieveResourceContextInput(BaseModel):
    resource_type: SearchableResourceType = Field(
        ...,
        description="Resource type: 'document', 'asset', or 'api_connector'",
    )
    resource_id: int = Field(..., description="The resource identifier (document ID, asset ID, or operation ID)")
    chunk_indexes: list[int] = Field(
        ...,
        min_length=1,
        max_length=MAX_RETRIEVE_CHUNK_INDEXES,
        description=(
            "Chunk indexes to fetch. Pick from search_documents hints. "
            "When only one index is provided, the server also fetches ±1 neighbors."
        ),
    )


def _get_runtime(config: RunnableConfig) -> _SearchRuntime:
    runtime = extract_runtime_context(config)
    profile = runtime.capability_profile
    return _SearchRuntime(
        tenant_id=runtime.user.tenant_id,
        user_id=runtime.user.user_id,
        user_role=runtime.user.role,
        tenant_config=runtime.tenant.config,
        collection_ids=profile.allowed_collection_ids if profile else None,
        data_source_ids=profile.allowed_data_source_ids if profile else None,
        api_ids=profile.allowed_api_connector_ids if profile else None,
        delegate=bool(profile.delegate) if profile else False,
    )


def _search_service(session, runtime: _SearchRuntime) -> SearchService:
    return SearchService(
        tenant_id=runtime.tenant_id,
        session=session,
        user_id=runtime.user_id,
        user_role=runtime.user_role,
        tenant_config=runtime.tenant_config,
        allowed_collection_ids=runtime.collection_ids,
        allowed_data_source_ids=runtime.data_source_ids,
        allowed_api_connector_ids=runtime.api_ids,
        delegate=runtime.delegate,
    )


def _service_actor(service: SearchService) -> ActorContext:
    return ActorContext(
        tenant_id=service.tenant_id,
        user_id=service.user_id,
        user_role=service.user_role,
    )


def _search_payload(query: str, page_items: list[Any], pagination: PaginationRequest) -> dict:
    has_next = pagination.page < min(pagination.total_pages, MAX_SEARCH_PAGE)
    return {
        "query": query,
        "page": pagination.page,
        "page_size": pagination.page_size,
        "total": pagination.total,
        "items": [item.model_dump(mode="json") for item in page_items],
        "has_next": has_next,
        "next_page": pagination.page + 1 if has_next else None,
    }


async def _run_search(
    config: RunnableConfig,
    *,
    tool_name: str,
    query: str,
    page: int,
    page_size: int,
    search_fn: SearchFn,
) -> ToolResult:
    runtime = _get_runtime(config)
    logger.info("%s tenant=%s user_id=%s query=%s", tool_name, runtime.tenant_id, runtime.user_id, query[:80])

    async with app_db_session() as session:
        service = _search_service(session, runtime)
        page_items, pagination = await search_fn(service, query, page, page_size)

    return ToolResult.success(_search_payload(query, page_items, pagination))


@tool(args_schema=SearchDocumentsInput)
async def search_documents(
    query: str,
    config: RunnableConfig,
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> ToolResult:
    """Search uploaded documents with hybrid FTS + vector search.

    Returns lightweight metadata (title, snippet, score) plus up to 3 chunk_index hints
    with section_hint previews and page when available. Prefer one focused query,
    then one batch retrieve on the returned chunk_indexes.
    """
    return await _run_search(
        config,
        tool_name="search_documents",
        query=query,
        page=page,
        page_size=page_size,
        search_fn=lambda service, q, p, ps: service.search_documents(query=q, page=p, page_size=ps),
    )


@tool(args_schema=SearchDataAssetsInput)
async def search_data_assets(
    query: str,
    config: RunnableConfig,
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> ToolResult:
    """Search data asset metadata (tables, columns, descriptions).

    Returns lightweight metadata (name, type, description, score).
    Use retrieve_resource_context to expand full asset schema.
    """
    return await _run_search(
        config,
        tool_name="search_data_assets",
        query=query,
        page=page,
        page_size=page_size,
        search_fn=lambda service, q, p, ps: service.search_assets(query=q, page=p, page_size=ps),
    )


@tool(args_schema=SearchApisInput)
async def search_apis(
    query: str,
    config: RunnableConfig,
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> ToolResult:
    """Search API operations by keyword (path, summary, tags).

    Returns lightweight metadata (operation_uid, method, path, summary, connector_name).
    Use the api_connector tool (get_operation_detail) to expand full request/response schema.
    """
    return await _run_search(
        config,
        tool_name="search_apis",
        query=query,
        page=page,
        page_size=page_size,
        search_fn=lambda service, q, p, ps: service.search_api_connectors(query=q, page=p, page_size=ps),
    )


async def _retrieve_document(
    service: SearchService,
    resource_id: int,
    chunk_indexes: list[int],
) -> ToolResult:
    try:
        chunks = await service.get_resource_context_chunks_for_anchors(
            resource_type=RESOURCE_TYPE_DOCUMENT,
            resource_id=int(resource_id),
            chunk_indexes=chunk_indexes,
        )
    except DomainException as exc:
        return ToolResult.error_result(
            exc.message,
            code="CONTEXT_CHUNKS_NOT_FOUND",
            metadata={"metadata": exc.details},
        )

    return ToolResult.success(
        {
            "resource_type": RESOURCE_TYPE_DOCUMENT,
            "resource_id": resource_id,
            "chunk_indexes": chunk_indexes,
            "chunks": [chunk.model_dump(mode="json") for chunk in chunks],
        }
    )


async def _retrieve_asset(service: SearchService, resource_id: int) -> ToolResult:
    try:
        asset_id = int(resource_id)
    except ValueError:
        return ToolResult.error_result(
            f"Invalid asset ID format: {resource_id}",
            code="INVALID_RESOURCE_ID",
        )

    from apps.shared.data_source.asset_metadata_service import AssetMetadataService

    asset_service = AssetMetadataService(tenant_id=service.tenant_id, db_session=service.session)

    try:
        asset_domain, data_source = await asset_service.get_asset_by_id_for_actor(
            actor=_service_actor(service),
            asset_id=asset_id,
        )
    except DomainException as exc:
        return ToolResult.error_result(
            exc.message,
            code="ASSET_NOT_FOUND",
            metadata={"metadata": exc.details},
        )

    return ToolResult.success(
        {
            "resource_type": RESOURCE_TYPE_ASSET,
            "resource_id": resource_id,
            "asset": {
                "id": asset_domain.id,
                "asset_name": asset_domain.asset_name,
                "asset_type": asset_domain.asset_type,
                "description": asset_domain.resolved_description(),
                "columns": asset_domain.resolved_columns(),
                "row_count": asset_domain.row_count,
                "data_source": data_source,
            },
        }
    )


async def _retrieve_api_operation(service: SearchService, resource_id: int) -> ToolResult:
    from apps.shared.api_connector.service import ApiConnectorService

    connector_service = ApiConnectorService(tenant_id=service.tenant_id, db_session=service.session)

    try:
        op, connector = await connector_service.get_operation_by_id_for_actor(
            operation_id=resource_id,
            actor=_service_actor(service),
            delegated_ids=(service.allowed_api_connector_ids if getattr(service, "delegate", False) else None),
        )
        if service.allowed_api_connector_ids is not None and connector.id not in service.allowed_api_connector_ids:
            return ToolResult.error_result("API operation not found", code="API_OPERATION_NOT_FOUND")
    except DomainException as exc:
        return ToolResult.error_result(
            exc.message,
            code="API_OPERATION_NOT_FOUND",
            metadata={"metadata": exc.details},
        )

    return ToolResult.success(
        {
            "resource_type": RESOURCE_TYPE_API_CONNECTOR,
            "resource_id": resource_id,
            "operation": {
                "operation_uid": op.operation_uid,
                "operation_id": op.id,
                "connector_id": connector.id,
                "connector_name": connector.name,
                "connector_base_url": connector.base_url,
                "method": op.method,
                "path_template": op.path_template,
                "summary": op.summary,
                "description": op.description,
                "tags": op.tags,
                "request_schema": op.request_schema,
                "response_schema": op.response_schema,
            },
        }
    )


@tool(args_schema=RetrieveResourceContextInput)
async def retrieve_resource_context(
    resource_type: SearchableResourceType,
    resource_id: int,
    config: RunnableConfig,
    chunk_indexes: list[int],
) -> ToolResult:
    """Retrieve detailed context for a specific resource.

    Resource-type-specific behavior:
    - document: Fetch the requested chunk_indexes from search_documents hints.
      One index also pulls ±1 neighbors automatically. Pass multiple indexes when
      a section spans several chunks. Image chunks are excluded from agent context.
    - asset: Returns full asset metadata (schema, columns, description).
      Ignores chunk_indexes.
    - api_connector: Returns full operation schema with request/response schemas.
      Ignores chunk_indexes.

    Use after search to expand search hits into full context.
    """
    runtime = _get_runtime(config)
    logger.info(
        "retrieve_resource_context tenant=%s resource_type=%s resource_id=%s",
        runtime.tenant_id,
        resource_type,
        resource_id,
    )

    async with app_db_session() as session:
        service = _search_service(session, runtime)

        if resource_type == RESOURCE_TYPE_DOCUMENT:
            return await _retrieve_document(service, resource_id, chunk_indexes)
        if resource_type == RESOURCE_TYPE_ASSET:
            return await _retrieve_asset(service, resource_id)
        if resource_type == RESOURCE_TYPE_API_CONNECTOR:
            return await _retrieve_api_operation(service, resource_id)

    return ToolResult.error_result(f"Unhandled resource_type: {resource_type}", code="INTERNAL_ERROR")
