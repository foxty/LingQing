"""RAG tools for internal and external retrieval workflows.

Provides granular search tools for documents, assets, and API operations,
plus a unified context retrieval tool for expanding resource details.
"""

from __future__ import annotations

import os

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from apps.shared.core.exceptions import DomainException
from apps.shared.db.session import app_db_session
from apps.shared.domain.types import (
    RESOURCE_TYPE_API_CONNECTOR,
    RESOURCE_TYPE_ASSET,
    RESOURCE_TYPE_DOCUMENT,
    SearchableResourceType,
)
from apps.shared.search import SearchService
from apps.shared.search.schemas import ResourceContextChunk, SearchTarget
from apps.shared.utils.logger import get_logger
from apps.tenant_app_service.agents.context import extract_runtime_context
from apps.tenant_app_service.agents.tools.tool_result import ToolResult

logger = get_logger(__name__)

MAX_SEARCH_PAGE = 5
DEFAULT_PAGE_SIZE = 10
MAX_PAGE_SIZE = 20

SOURCE_DOCUMENT = SearchTarget.DOCUMENT
SOURCE_ASSET = SearchTarget.ASSET
SOURCE_API_CONNECTOR = SearchTarget.API_CONNECTOR
SOURCE_WEB = "web"

INTERNAL_SOURCES = {SOURCE_DOCUMENT, SOURCE_ASSET, SOURCE_API_CONNECTOR}


RESOURCE_TYPES = {RESOURCE_TYPE_DOCUMENT, RESOURCE_TYPE_ASSET, RESOURCE_TYPE_API_CONNECTOR}


class SearchDocumentsInput(BaseModel):
    query: str = Field(..., min_length=1, description="Search query")
    page: int = Field(default=1, ge=1, le=MAX_SEARCH_PAGE)
    page_size: int = Field(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE)


class SearchDataAssetsInput(BaseModel):
    query: str = Field(..., min_length=1, description="Search query")
    page: int = Field(default=1, ge=1, le=MAX_SEARCH_PAGE)
    page_size: int = Field(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE)


class SearchApisInput(BaseModel):
    query: str = Field(..., min_length=1, description="Search query")
    page: int = Field(default=1, ge=1, le=MAX_SEARCH_PAGE)
    page_size: int = Field(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE)


class SearchWebInput(BaseModel):
    query: str = Field(..., min_length=1, description="Web search query")
    page: int = Field(default=1, ge=1, le=MAX_SEARCH_PAGE)
    page_size: int = Field(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE)


class RetrieveResourceContextInput(BaseModel):
    resource_type: SearchableResourceType = Field(
        ...,
        description="Resource type: 'document', 'asset', or 'api_connector'",
    )
    resource_id: int = Field(..., description="The resource identifier (document ID, asset ID, or operation ID)")
    chunk_indexes: list[int] | None = Field(
        default=None,
        description="1-3 anchor chunk indexes for document context retrieval (merged, deduplicated)",
    )
    context_range: int = Field(
        default=2,
        ge=1,
        le=10,
        description=(
            "Number of chunks to fetch around each anchor (documents only). "
            "Use 4-5 when listing or enumerating items from a document section."
        ),
    )


def _get_runtime(config: RunnableConfig):
    runtime = extract_runtime_context(config)
    profile = runtime.capability_profile
    return (
        runtime.user.tenant_id,
        runtime.user.user_id,
        runtime.user.role,
        runtime.tenant.config,
        profile.allowed_collection_ids if profile else None,
        profile.allowed_data_source_ids if profile else None,
        profile.allowed_api_connector_ids if profile else None,
        bool(profile.delegate) if profile else False,
    )


def _search_service(
    session,
    tenant_id,
    user_id,
    user_role,
    tenant_config,
    collection_ids=None,
    data_source_ids=None,
    api_ids=None,
    delegate=False,
):
    return SearchService(
        tenant_id=tenant_id,
        session=session,
        user_id=user_id,
        user_role=user_role,
        tenant_config=tenant_config,
        allowed_collection_ids=collection_ids,
        allowed_data_source_ids=data_source_ids,
        allowed_api_connector_ids=api_ids,
        delegate=delegate,
    )


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
    (
        tenant_id,
        user_id,
        user_role,
        tenant_config,
        collection_ids,
        data_source_ids,
        api_ids,
        delegate,
    ) = _get_runtime(config)

    logger.info("search_documents tenant=%s user_id=%s query=%s", tenant_id, user_id, query[:80])

    async with app_db_session() as session:
        service = _search_service(
            session,
            tenant_id,
            user_id,
            user_role,
            tenant_config,
            collection_ids,
            data_source_ids,
            api_ids,
            delegate,
        )
        page_items, pagination = await service.search_documents(
            query=query,
            page=page,
            page_size=page_size,
        )

    has_next = pagination.page < min(pagination.total_pages, MAX_SEARCH_PAGE)

    payload = {
        "query": query,
        "page": pagination.page,
        "page_size": pagination.page_size,
        "total": pagination.total,
        "items": [item.model_dump(mode="json") for item in page_items],
        "has_next": has_next,
        "next_page": pagination.page + 1 if has_next else None,
    }
    return ToolResult.success(payload)


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
    (
        tenant_id,
        user_id,
        user_role,
        tenant_config,
        collection_ids,
        data_source_ids,
        api_ids,
        delegate,
    ) = _get_runtime(config)

    logger.info("search_data_assets tenant=%s user_id=%s query=%s", tenant_id, user_id, query[:80])

    async with app_db_session() as session:
        service = _search_service(
            session,
            tenant_id,
            user_id,
            user_role,
            tenant_config,
            collection_ids,
            data_source_ids,
            api_ids,
            delegate,
        )
        page_items, pagination = await service.search_assets(
            query=query,
            page=page,
            page_size=page_size,
        )

    has_next = pagination.page < min(pagination.total_pages, MAX_SEARCH_PAGE)

    payload = {
        "query": query,
        "page": pagination.page,
        "page_size": pagination.page_size,
        "total": pagination.total,
        "items": [item.model_dump(mode="json") for item in page_items],
        "has_next": has_next,
        "next_page": pagination.page + 1 if has_next else None,
    }
    return ToolResult.success(payload)


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
    (
        tenant_id,
        user_id,
        user_role,
        tenant_config,
        collection_ids,
        data_source_ids,
        api_ids,
        delegate,
    ) = _get_runtime(config)

    logger.info("search_apis tenant=%s user_id=%s query=%s", tenant_id, user_id, query[:80])

    async with app_db_session() as session:
        service = _search_service(
            session,
            tenant_id,
            user_id,
            user_role,
            tenant_config,
            collection_ids,
            data_source_ids,
            api_ids,
            delegate,
        )
        page_items, pagination = await service.search_api_connectors(
            query=query,
            page=page,
            page_size=page_size,
        )

    has_next = pagination.page < min(pagination.total_pages, MAX_SEARCH_PAGE)

    payload = {
        "query": query,
        "page": pagination.page,
        "page_size": pagination.page_size,
        "total": pagination.total,
        "items": [item.model_dump(mode="json") for item in page_items],
        "has_next": has_next,
        "next_page": pagination.page + 1 if has_next else None,
    }
    return ToolResult.success(payload)


@tool(args_schema=RetrieveResourceContextInput)
async def retrieve_resource_context(
    resource_type: SearchableResourceType,
    resource_id: int,
    config: RunnableConfig,
    chunk_indexes: list[int] | None = None,
    context_range: int = 2,
) -> ToolResult:
    """Retrieve detailed context for a specific resource.

    Resource-type-specific behavior:
    - document: Returns text chunks around 1-3 chunk_indexes ± context_range in one call,
      plus all chunks on the same page as each anchor (merged and deduplicated).
      Prefer context_range=4-5 for list/enumeration tasks.
      Image chunks include image_url and image_markdown. The images list repeats deduped image
      chunks (same shape as chunks[]) so you can scan figures quickly. Use content as the label.
      Copy image_markdown from the matching chunk into the reply so the UI can render it.
    - asset: Returns full asset metadata (schema, columns, description).
      Ignores chunk_indexes/context_range.
    - api_connector: Returns full operation schema with request/response schemas.
      Ignores chunk_indexes/context_range.

    Use after search to expand search hits into full context.
    """
    (
        tenant_id,
        user_id,
        user_role,
        tenant_config,
        collection_ids,
        data_source_ids,
        api_ids,
        delegate,
    ) = _get_runtime(config)

    logger.info(
        "retrieve_resource_context tenant=%s resource_type=%s resource_id=%s",
        tenant_id,
        resource_type,
        resource_id,
    )

    async with app_db_session() as session:
        service = _search_service(
            session,
            tenant_id,
            user_id,
            user_role,
            tenant_config,
            collection_ids,
            data_source_ids,
            api_ids,
            delegate,
        )

        if resource_type == RESOURCE_TYPE_DOCUMENT:
            if not chunk_indexes:
                return ToolResult.error_result(
                    "chunk_indexes is required for document resource type",
                    code="INVALID_ARGUMENT",
                )
            if len(chunk_indexes) > 3:
                return ToolResult.error_result(
                    "chunk_indexes supports at most 3 anchors",
                    code="INVALID_ARGUMENT",
                )
            return await _retrieve_document_context(service, resource_id, chunk_indexes, context_range)
        if resource_type == RESOURCE_TYPE_ASSET:
            return await _retrieve_asset_context(service, resource_id)
        if resource_type == RESOURCE_TYPE_API_CONNECTOR:
            return await _retrieve_api_operation_context(service, resource_id)

    # Should not reach here
    return ToolResult.error_result(f"Unhandled resource_type: {resource_type}", code="INTERNAL_ERROR")


def _deduped_image_chunks(chunks: list[ResourceContextChunk]) -> list[dict]:
    by_url: dict[str, ResourceContextChunk] = {}
    for chunk in chunks:
        if chunk.block_type == "image" and chunk.image_url:
            by_url.setdefault(chunk.image_url, chunk)
    return [chunk.model_dump(mode="json") for chunk in by_url.values()]


async def _retrieve_document_context(
    service: SearchService,
    resource_id: int,
    chunk_indexes: list[int],
    context_range: int,
) -> ToolResult:
    doc_id = int(resource_id)

    try:
        chunks = await service.get_resource_context_chunks_for_anchors(
            resource_type=RESOURCE_TYPE_DOCUMENT,
            resource_id=doc_id,
            chunk_indexes=chunk_indexes,
            context_range=context_range,
        )
    except DomainException as exc:
        return ToolResult.error_result(
            exc.message,
            code="CONTEXT_CHUNKS_NOT_FOUND",
            metadata={"metadata": exc.details},
        )

    payload = {
        "resource_type": RESOURCE_TYPE_DOCUMENT,
        "resource_id": resource_id,
        "anchor_chunk_indexes": chunk_indexes,
        "context_range": context_range,
        "chunks": [chunk.model_dump(mode="json") for chunk in chunks],
        "images": _deduped_image_chunks(chunks),
    }
    return ToolResult.success(payload)


async def _retrieve_asset_context(service: SearchService, resource_id: int) -> ToolResult:
    """Retrieve full asset metadata by asset ID."""
    try:
        asset_id = int(resource_id)
    except ValueError:
        return ToolResult.error_result(
            f"Invalid asset ID format: {resource_id}",
            code="INVALID_RESOURCE_ID",
        )

    from apps.shared.data_source.asset_metadata_service import AssetMetadataService
    from apps.shared.domain.actor import ActorContext

    actor = ActorContext(
        tenant_id=service.tenant_id,
        user_id=service.user_id,
        user_role=service.user_role,
    )
    asset_service = AssetMetadataService(tenant_id=service.tenant_id, db_session=service.session)

    try:
        asset_domain, data_source = await asset_service.get_asset_by_id_for_actor(actor=actor, asset_id=asset_id)
    except DomainException as exc:
        return ToolResult.error_result(
            exc.message,
            code="ASSET_NOT_FOUND",
            metadata={"metadata": exc.details},
        )

    payload = {
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
    return ToolResult.success(payload)


async def _retrieve_api_operation_context(
    service: SearchService,
    resource_id: int,
) -> ToolResult:
    """Retrieve full API operation schema by operation ID."""
    from apps.shared.api_connector.service import ApiConnectorService
    from apps.shared.domain.actor import ActorContext

    actor = ActorContext(
        tenant_id=service.tenant_id,
        user_id=service.user_id,
        user_role=service.user_role,
    )
    connector_service = ApiConnectorService(tenant_id=service.tenant_id, db_session=service.session)

    try:
        op, connector = await connector_service.get_operation_by_id_for_actor(
            operation_id=resource_id,
            actor=actor,
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

    payload = {
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
    return ToolResult.success(payload)


# @tool(args_schema=SearchWebInput)
async def search_web(
    query: str,
    config: RunnableConfig,
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> ToolResult:
    """Search public web content (scaffolded).

    This tool is intentionally feature-gated and returns a controlled error
    until a web provider is configured.
    """
    _runtime = extract_runtime_context(config)
    enabled = os.getenv("ENABLE_AGENT_WEB_SEARCH", "false").strip().lower() == "true"

    if not enabled:
        return ToolResult.error_result(
            "Web search is disabled.",
            code="WEB_SEARCH_DISABLED",
            hint="Set ENABLE_AGENT_WEB_SEARCH=true and configure a web search provider.",
            metadata={"metadata": {"query": query, "page": page, "page_size": page_size}},
        )

    return ToolResult.error_result(
        "Web search provider is not implemented yet.",
        code="WEB_SEARCH_NOT_IMPLEMENTED",
        hint="Configure a concrete provider implementation before enabling web retrieval.",
        metadata={"metadata": {"query": query, "page": page, "page_size": page_size}},
    )
