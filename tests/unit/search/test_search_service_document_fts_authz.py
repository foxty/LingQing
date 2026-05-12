"""Tests for document FTS search collection authz pushdown."""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from apps.shared.document.collection_service import DocumentAccessScope
from apps.shared.search.search_service import SearchService


@pytest.mark.asyncio
async def test_search_documents_fts_passes_index_parent_filter():
    service = SearchService.__new__(SearchService)
    service.tenant_id = 1
    service.session = AsyncMock()
    service.resource_index_repo = AsyncMock()
    service.resource_index_repo.search_documents_fts = AsyncMock(return_value=[])

    index_filter = object()
    await service._search_documents_fts("query", k=5, index_abac_filter=index_filter)

    service.resource_index_repo.search_documents_fts.assert_awaited_once_with(
        tenant_id=1,
        query="query",
        limit=5,
        abac_filter=index_filter,
    )


@pytest.mark.asyncio
async def test_search_documents_hybrid_uses_separate_fts_and_document_filters():
    service = SearchService.__new__(SearchService)
    service.tenant_id = 1
    service.session = AsyncMock()

    index_filter = object()
    document_filter = object()
    service._search_documents_fts = AsyncMock(return_value=[])
    service._search_documents_vector = AsyncMock(return_value=[])

    await service._search_documents_hybrid(
        "fts query",
        "vector query",
        k=3,
        index_abac_filter=index_filter,
        document_abac_filter=document_filter,
    )

    service._search_documents_fts.assert_awaited_once_with("fts query", 6, index_filter)
    service._search_documents_vector.assert_awaited_once_with("vector query", 6, document_filter)


@pytest.mark.asyncio
async def test_search_documents_uses_access_scope_filters(monkeypatch):
    service = SearchService.__new__(SearchService)
    service.tenant_id = 1
    service.user_id = 2
    service.user_role = "member"
    service.session = AsyncMock()

    index_filter = object()
    document_filter = object()
    scope = DocumentAccessScope(
        deny_all=False,
        allow_all=False,
        document_filter=document_filter,
        index_parent_filter=index_filter,
    )
    service._get_document_access_scope = AsyncMock(return_value=scope)
    service._search_documents_hybrid = AsyncMock(return_value=[])
    service._document_to_item = lambda result: result

    await service.search_documents(f"query-{uuid4().hex[:6]}", page=1, page_size=10)

    service._search_documents_hybrid.assert_awaited_once()
    kwargs = service._search_documents_hybrid.await_args.kwargs
    assert kwargs["index_abac_filter"] is index_filter
    assert kwargs["document_abac_filter"] is document_filter


@pytest.mark.asyncio
async def test_get_resource_context_chunks_checks_document_collection_authz(monkeypatch):
    from apps.shared.core.exceptions import AuthorizationError
    from apps.shared.domain.types import RESOURCE_TYPE_DOCUMENT

    service = SearchService.__new__(SearchService)
    service.tenant_id = 1
    service.user_id = 2
    service.user_role = "member"
    service.session = AsyncMock()
    service.rag_manager = AsyncMock()

    collection_service = AsyncMock()
    collection_service.require_document_access = AsyncMock(side_effect=AuthorizationError("denied"))

    monkeypatch.setattr(
        "apps.shared.search.search_service.DocumentCollectionService",
        lambda tenant_id, session: collection_service,
    )

    with pytest.raises(AuthorizationError):
        await service.get_resource_context_chunks(
            resource_type=RESOURCE_TYPE_DOCUMENT,
            resource_id=99,
            chunk_index=0,
            context_range=1,
        )

    collection_service.require_document_access.assert_awaited_once()
    service.rag_manager.get_context_chunks_by_resource.assert_not_called()
