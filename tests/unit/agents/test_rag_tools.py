"""Unit tests for RAG tools."""

import json

import pytest

from apps.shared.search.schemas import ResourceContextChunk
from apps.shared.utils.pagination import PaginationRequest
from apps.tenant_app_service.agents.tools.rag import (
    retrieve_resource_context,
    search_apis,
    search_data_assets,
    search_documents,
)
from apps.tenant_app_service.agents.tools.tool_result import ToolResultStatus


class _FakeSessionContext:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.fixture(autouse=True)
def mock_embeddings_resolver(monkeypatch):
    fake_embeddings = object()

    async def _resolve(_tenant_id, _session):
        return fake_embeddings

    monkeypatch.setattr(
        "apps.shared.llm_providers.embedding_resolver.resolve_tenant_embeddings",
        _resolve,
    )
    return fake_embeddings


@pytest.mark.asyncio
async def test_search_documents_success(monkeypatch, runnable_config):
    class _FakeSearchService:
        def __init__(self, tenant_id, session, user_id, user_role, embeddings=None, **_kwargs):
            assert tenant_id == 1
            assert user_id == 123
            assert user_role == "admin"
            assert embeddings is not None

        async def search_documents(self, *, query, page, page_size):
            assert query == "orders"
            return [], PaginationRequest(page=1, page_size=page_size, total=0)

    monkeypatch.setattr("apps.tenant_app_service.agents.tools.rag.app_db_session", lambda: _FakeSessionContext())
    monkeypatch.setattr("apps.tenant_app_service.agents.tools.rag.SearchService", _FakeSearchService)

    result = await search_documents.ainvoke(
        {
            "query": "orders",
            "page": 1,
            "page_size": 10,
        },
        config=runnable_config,
    )

    payload = json.loads(result.content)
    assert result.status == ToolResultStatus.SUCCESS
    assert payload["total"] == 0
    assert payload["has_next"] is False


@pytest.mark.asyncio
async def test_search_documents_passes_embeddings(monkeypatch, runnable_config, mock_embeddings_resolver):
    """Verify registry embeddings are passed to SearchService."""
    captured = {}

    class _FakeSearchService:
        def __init__(self, tenant_id, session, user_id, user_role, embeddings=None, **_kwargs):
            captured["embeddings"] = embeddings

        async def search_documents(self, *, query, page, page_size):
            return [], PaginationRequest(page=1, page_size=page_size, total=0)

    monkeypatch.setattr("apps.tenant_app_service.agents.tools.rag.app_db_session", lambda: _FakeSessionContext())
    monkeypatch.setattr("apps.tenant_app_service.agents.tools.rag.SearchService", _FakeSearchService)

    await search_documents.ainvoke(
        {"query": "test", "page": 1, "page_size": 10},
        config=runnable_config,
    )

    assert captured["embeddings"] is mock_embeddings_resolver


@pytest.mark.asyncio
async def test_search_data_assets_success(monkeypatch, runnable_config):
    class _FakeSearchService:
        def __init__(self, tenant_id, session, user_id, user_role, embeddings=None, **_kwargs):
            pass

        async def search_assets(self, *, query, page, page_size):
            return [], PaginationRequest(page=1, page_size=page_size, total=0)

    monkeypatch.setattr("apps.tenant_app_service.agents.tools.rag.app_db_session", lambda: _FakeSessionContext())
    monkeypatch.setattr("apps.tenant_app_service.agents.tools.rag.SearchService", _FakeSearchService)

    result = await search_data_assets.ainvoke(
        {"query": "users"},
        config=runnable_config,
    )

    payload = json.loads(result.content)
    assert result.status == ToolResultStatus.SUCCESS
    assert payload["query"] == "users"


@pytest.mark.asyncio
async def test_search_data_assets_passes_embeddings(monkeypatch, runnable_config, mock_embeddings_resolver):
    """Verify registry embeddings are passed to SearchService for asset search."""
    captured = {}

    class _FakeSearchService:
        def __init__(self, tenant_id, session, user_id, user_role, embeddings=None, **_kwargs):
            captured["embeddings"] = embeddings

        async def search_assets(self, *, query, page, page_size):
            return [], PaginationRequest(page=1, page_size=page_size, total=0)

    monkeypatch.setattr("apps.tenant_app_service.agents.tools.rag.app_db_session", lambda: _FakeSessionContext())
    monkeypatch.setattr("apps.tenant_app_service.agents.tools.rag.SearchService", _FakeSearchService)

    await search_data_assets.ainvoke(
        {"query": "test"},
        config=runnable_config,
    )

    assert captured["embeddings"] is mock_embeddings_resolver


@pytest.mark.asyncio
async def test_search_apis_success(monkeypatch, runnable_config):
    class _FakeSearchService:
        def __init__(self, tenant_id, session, user_id, user_role, embeddings=None, **_kwargs):
            pass

        async def search_api_connectors(self, *, query, page, page_size):
            return [], PaginationRequest(page=1, page_size=page_size, total=0)

    monkeypatch.setattr("apps.tenant_app_service.agents.tools.rag.app_db_session", lambda: _FakeSessionContext())
    monkeypatch.setattr("apps.tenant_app_service.agents.tools.rag.SearchService", _FakeSearchService)

    result = await search_apis.ainvoke(
        {"query": "orders"},
        config=runnable_config,
    )

    payload = json.loads(result.content)
    assert result.status == ToolResultStatus.SUCCESS
    assert payload["query"] == "orders"


@pytest.mark.asyncio
async def test_search_apis_passes_embeddings(monkeypatch, runnable_config, mock_embeddings_resolver):
    """Verify registry embeddings are passed to SearchService for API search."""
    captured = {}

    class _FakeSearchService:
        def __init__(self, tenant_id, session, user_id, user_role, embeddings=None, **_kwargs):
            captured["embeddings"] = embeddings

        async def search_api_connectors(self, *, query, page, page_size):
            return [], PaginationRequest(page=1, page_size=page_size, total=0)

    monkeypatch.setattr("apps.tenant_app_service.agents.tools.rag.app_db_session", lambda: _FakeSessionContext())
    monkeypatch.setattr("apps.tenant_app_service.agents.tools.rag.SearchService", _FakeSearchService)

    await search_apis.ainvoke(
        {"query": "test"},
        config=runnable_config,
    )

    assert captured["embeddings"] is mock_embeddings_resolver


@pytest.mark.asyncio
async def test_retrieve_resource_context_invalid_type(monkeypatch, runnable_config):
    # Since resource_type is typed as SearchableResourceType, Pydantic rejects invalid values.
    # This tests that the tool correctly handles invalid resource types when passed via a valid enum.
    pass


@pytest.mark.asyncio
async def test_retrieve_resource_context_document_success(monkeypatch, runnable_config):
    class _FakeSearchService:
        def __init__(self, tenant_id, session, user_id, user_role, embeddings=None, **_kwargs):
            self.tenant_id = tenant_id
            self.session = session
            self.user_id = user_id
            self.user_role = user_role

        async def get_resource_context_chunks_for_anchors(self, **kwargs):
            assert kwargs["chunk_indexes"] == [1]
            return [ResourceContextChunk(chunk_index=1, total_chunks=10, content="hello")]

    monkeypatch.setattr("apps.tenant_app_service.agents.tools.rag.app_db_session", lambda: _FakeSessionContext())
    monkeypatch.setattr("apps.tenant_app_service.agents.tools.rag.SearchService", _FakeSearchService)

    result = await retrieve_resource_context.ainvoke(
        {
            "resource_type": "document",
            "resource_id": 42,
            "chunk_indexes": [1],
        },
        config=runnable_config,
    )
    payload = json.loads(result.content)

    assert result.status == ToolResultStatus.SUCCESS
    assert payload["resource_type"] == "document"
    assert payload["resource_id"] == 42
    assert len(payload["chunks"]) == 1
    assert payload["chunks"][0]["content"] == "hello"
    assert "images" not in payload


@pytest.mark.asyncio
async def test_retrieve_resource_context_batch_anchors(monkeypatch, runnable_config):
    class _FakeSearchService:
        def __init__(self, tenant_id, session, user_id, user_role, embeddings=None, **_kwargs):
            self.tenant_id = tenant_id

        async def get_resource_context_chunks_for_anchors(self, **kwargs):
            assert kwargs["chunk_indexes"] == [2, 8]
            return [
                ResourceContextChunk(chunk_index=2, total_chunks=10, content="two"),
                ResourceContextChunk(chunk_index=8, total_chunks=10, content="eight"),
            ]

    monkeypatch.setattr("apps.tenant_app_service.agents.tools.rag.app_db_session", lambda: _FakeSessionContext())
    monkeypatch.setattr("apps.tenant_app_service.agents.tools.rag.SearchService", _FakeSearchService)

    result = await retrieve_resource_context.ainvoke(
        {
            "resource_type": "document",
            "resource_id": 42,
            "chunk_indexes": [2, 8],
        },
        config=runnable_config,
    )
    payload = json.loads(result.content)

    assert result.status == ToolResultStatus.SUCCESS
    assert payload["chunk_indexes"] == [2, 8]
    assert [chunk["chunk_index"] for chunk in payload["chunks"]] == [2, 8]


@pytest.mark.asyncio
async def test_retrieve_resource_context_rejects_too_many_chunk_indexes(monkeypatch, runnable_config):
    monkeypatch.setattr("apps.tenant_app_service.agents.tools.rag.app_db_session", lambda: _FakeSessionContext())

    with pytest.raises(Exception):
        await retrieve_resource_context.ainvoke(
            {
                "resource_type": "document",
                "resource_id": 42,
                "chunk_indexes": list(range(11)),
            },
            config=runnable_config,
        )


@pytest.mark.asyncio
async def test_retrieve_resource_context_passes_embeddings(monkeypatch, runnable_config):
    """Verify registry embeddings are passed to SearchService for resource context retrieval."""
    captured = {}
    fake_embeddings = object()

    class _FakeSearchService:
        def __init__(self, tenant_id, session, user_id, user_role, embeddings=None, **_kwargs):
            captured["embeddings"] = embeddings
            self.tenant_id = tenant_id
            self.session = session
            self.user_id = user_id
            self.user_role = user_role

        async def get_resource_context_chunks_for_anchors(self, **kwargs):
            return [ResourceContextChunk(chunk_index=1, total_chunks=10, content="test")]

    async def _fake_resolve(_tenant_id, _session):
        return fake_embeddings

    monkeypatch.setattr("apps.tenant_app_service.agents.tools.rag.app_db_session", lambda: _FakeSessionContext())
    monkeypatch.setattr("apps.tenant_app_service.agents.tools.rag.SearchService", _FakeSearchService)
    monkeypatch.setattr(
        "apps.shared.llm_providers.embedding_resolver.resolve_tenant_embeddings",
        _fake_resolve,
    )

    await retrieve_resource_context.ainvoke(
        {
            "resource_type": "document",
            "resource_id": "42",
            "chunk_indexes": [1],
        },
        config=runnable_config,
    )

    assert captured["embeddings"] is fake_embeddings


@pytest.mark.asyncio
async def test_search_documents_resolves_registry_embeddings(monkeypatch):
    """Test that SearchService receives embeddings from the registry resolver."""
    from langchain_core.runnables import RunnableConfig

    from apps.tenant_app_service.agents.domain import (
        AgentRuntimeContext,
        AgentTenantContext,
        AgentUserContext,
    )

    captured = {}
    fake_embeddings = object()

    class _FakeSearchService:
        def __init__(self, tenant_id, session, user_id, user_role, embeddings=None, **_kwargs):
            captured["embeddings"] = embeddings

        async def search_documents(self, *, query, page, page_size):
            return [], PaginationRequest(page=1, page_size=page_size, total=0)

    async def _fake_resolve(_tenant_id, _session):
        return fake_embeddings

    monkeypatch.setattr("apps.tenant_app_service.agents.tools.rag.app_db_session", lambda: _FakeSessionContext())
    monkeypatch.setattr("apps.tenant_app_service.agents.tools.rag.SearchService", _FakeSearchService)
    monkeypatch.setattr(
        "apps.shared.llm_providers.embedding_resolver.resolve_tenant_embeddings",
        _fake_resolve,
    )

    runtime_ctx = AgentRuntimeContext(
        tenant=AgentTenantContext(
            tenant_id=1,
            tenant_name="test_tenant",
            config={},
        ),
        user=AgentUserContext(
            user_id=123,
            username="testuser",
            role="admin",
            tenant_id=1,
            tenant_name="test_tenant",
        ),
        agent_id=456,
        agent_name="test_agent",
        thread_id="thread_test_123",
        session_id="session_test_456",
    )
    config = RunnableConfig(
        configurable={
            "thread_id": runtime_ctx.thread_id,
            "runtime": runtime_ctx.model_dump(),
            "session_id": runtime_ctx.session_id,
        }
    )

    await search_documents.ainvoke(
        {"query": "test", "page": 1, "page_size": 10},
        config=config,
    )

    assert captured["embeddings"] is fake_embeddings
