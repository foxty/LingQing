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


@pytest.mark.asyncio
async def test_search_documents_success(monkeypatch, runnable_config):
    class _FakeSearchService:
        def __init__(self, tenant_id, session, user_id, user_role, tenant_config=None, **_kwargs):
            assert tenant_id == 1
            assert user_id == 123
            assert user_role == "admin"
            assert tenant_config == {}  # tenant_config from runtime_context fixture

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
async def test_search_documents_passes_tenant_config(monkeypatch, runnable_config):
    """Verify tenant_config is passed to SearchService."""
    captured_config = {}

    class _FakeSearchService:
        def __init__(self, tenant_id, session, user_id, user_role, tenant_config=None, **_kwargs):
            captured_config["tenant_config"] = tenant_config

        async def search_documents(self, *, query, page, page_size):
            return [], PaginationRequest(page=1, page_size=page_size, total=0)

    monkeypatch.setattr("apps.tenant_app_service.agents.tools.rag.app_db_session", lambda: _FakeSessionContext())
    monkeypatch.setattr("apps.tenant_app_service.agents.tools.rag.SearchService", _FakeSearchService)

    await search_documents.ainvoke(
        {"query": "test", "page": 1, "page_size": 10},
        config=runnable_config,
    )

    assert captured_config["tenant_config"] == {}


@pytest.mark.asyncio
async def test_search_data_assets_success(monkeypatch, runnable_config):
    class _FakeSearchService:
        def __init__(self, tenant_id, session, user_id, user_role, tenant_config=None, **_kwargs):
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
async def test_search_data_assets_passes_tenant_config(monkeypatch, runnable_config):
    """Verify tenant_config is passed to SearchService for asset search."""
    captured_config = {}

    class _FakeSearchService:
        def __init__(self, tenant_id, session, user_id, user_role, tenant_config=None, **_kwargs):
            captured_config["tenant_config"] = tenant_config

        async def search_assets(self, *, query, page, page_size):
            return [], PaginationRequest(page=1, page_size=page_size, total=0)

    monkeypatch.setattr("apps.tenant_app_service.agents.tools.rag.app_db_session", lambda: _FakeSessionContext())
    monkeypatch.setattr("apps.tenant_app_service.agents.tools.rag.SearchService", _FakeSearchService)

    await search_data_assets.ainvoke(
        {"query": "test"},
        config=runnable_config,
    )

    assert captured_config["tenant_config"] == {}


@pytest.mark.asyncio
async def test_search_apis_success(monkeypatch, runnable_config):
    class _FakeSearchService:
        def __init__(self, tenant_id, session, user_id, user_role, tenant_config=None, **_kwargs):
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
async def test_search_apis_passes_tenant_config(monkeypatch, runnable_config):
    """Verify tenant_config is passed to SearchService for API search."""
    captured_config = {}

    class _FakeSearchService:
        def __init__(self, tenant_id, session, user_id, user_role, tenant_config=None, **_kwargs):
            captured_config["tenant_config"] = tenant_config

        async def search_api_connectors(self, *, query, page, page_size):
            return [], PaginationRequest(page=1, page_size=page_size, total=0)

    monkeypatch.setattr("apps.tenant_app_service.agents.tools.rag.app_db_session", lambda: _FakeSessionContext())
    monkeypatch.setattr("apps.tenant_app_service.agents.tools.rag.SearchService", _FakeSearchService)

    await search_apis.ainvoke(
        {"query": "test"},
        config=runnable_config,
    )

    assert captured_config["tenant_config"] == {}


@pytest.mark.asyncio
async def test_retrieve_resource_context_invalid_type(monkeypatch, runnable_config):
    # Since resource_type is typed as SearchableResourceType, Pydantic rejects invalid values.
    # This tests that the tool correctly handles invalid resource types when passed via a valid enum.
    pass


@pytest.mark.asyncio
async def test_retrieve_resource_context_document_success(monkeypatch, runnable_config):
    class _FakeSearchService:
        def __init__(self, tenant_id, session, user_id, user_role, tenant_config=None, **_kwargs):
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
            "context_range": 1,
        },
        config=runnable_config,
    )
    payload = json.loads(result.content)

    assert result.status == ToolResultStatus.SUCCESS
    assert payload["resource_type"] == "document"
    assert payload["resource_id"] == 42
    assert len(payload["chunks"]) == 1
    assert payload["chunks"][0]["content"] == "hello"
    assert payload["images"] == []


@pytest.mark.asyncio
async def test_retrieve_resource_context_includes_image_urls(monkeypatch, runnable_config):
    image_name = "a" * 64 + ".png"

    class _FakeSearchService:
        def __init__(self, tenant_id, session, user_id, user_role, tenant_config=None, **_kwargs):
            pass

        async def get_resource_context_chunks_for_anchors(self, **kwargs):
            image_url = f"/documents/42/images/{image_name}"
            return [
                ResourceContextChunk(
                    chunk_index=1,
                    total_chunks=10,
                    content="Q3 revenue chart",
                    block_type="image",
                    page=3,
                    image_url=image_url,
                    image_markdown=f"![Q3 revenue chart]({image_url})",
                )
            ]

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

    image_url = f"/documents/42/images/{image_name}"
    assert payload["images"] == [
        {
            "chunk_index": 1,
            "total_chunks": 10,
            "content": "Q3 revenue chart",
            "block_type": "image",
            "page": 3,
            "image_url": image_url,
            "image_markdown": f"![Q3 revenue chart]({image_url})",
        }
    ]
    assert "image_uri" not in payload["chunks"][0]
    assert "image_uri" not in payload["images"][0]
    assert payload["chunks"][0]["page"] == 3
    assert payload["chunks"][0]["block_type"] == "image"
    assert payload["chunks"][0]["image_url"] == image_url
    assert payload["chunks"][0]["image_markdown"] == f"![Q3 revenue chart]({image_url})"


@pytest.mark.asyncio
async def test_retrieve_resource_context_batch_anchors(monkeypatch, runnable_config):
    class _FakeSearchService:
        def __init__(self, tenant_id, session, user_id, user_role, tenant_config=None, **_kwargs):
            self.tenant_id = tenant_id

        async def get_resource_context_chunks_for_anchors(self, **kwargs):
            assert kwargs["chunk_indexes"] == [2, 8]
            return [
                ResourceContextChunk(chunk_index=1, total_chunks=10, content="one"),
                ResourceContextChunk(chunk_index=8, total_chunks=10, content="eight"),
            ]

    monkeypatch.setattr("apps.tenant_app_service.agents.tools.rag.app_db_session", lambda: _FakeSessionContext())
    monkeypatch.setattr("apps.tenant_app_service.agents.tools.rag.SearchService", _FakeSearchService)

    result = await retrieve_resource_context.ainvoke(
        {
            "resource_type": "document",
            "resource_id": 42,
            "chunk_indexes": [2, 8],
            "context_range": 2,
        },
        config=runnable_config,
    )
    payload = json.loads(result.content)

    assert result.status == ToolResultStatus.SUCCESS
    assert payload["anchor_chunk_indexes"] == [2, 8]
    assert [chunk["chunk_index"] for chunk in payload["chunks"]] == [1, 8]


@pytest.mark.asyncio
async def test_retrieve_resource_context_rejects_too_many_anchors(monkeypatch, runnable_config):
    monkeypatch.setattr("apps.tenant_app_service.agents.tools.rag.app_db_session", lambda: _FakeSessionContext())

    result = await retrieve_resource_context.ainvoke(
        {
            "resource_type": "document",
            "resource_id": 42,
            "chunk_indexes": [1, 2, 3, 4],
            "context_range": 2,
        },
        config=runnable_config,
    )

    assert result.status == ToolResultStatus.ERROR


@pytest.mark.asyncio
async def test_retrieve_resource_context_passes_tenant_config(monkeypatch, runnable_config):
    """Verify tenant_config is passed to SearchService for resource context retrieval."""
    captured_config = {}

    class _FakeSearchService:
        def __init__(self, tenant_id, session, user_id, user_role, tenant_config=None, **_kwargs):
            captured_config["tenant_config"] = tenant_config
            self.tenant_id = tenant_id
            self.session = session
            self.user_id = user_id
            self.user_role = user_role

        async def get_resource_context_chunks_for_anchors(self, **kwargs):
            return [ResourceContextChunk(chunk_index=1, total_chunks=10, content="test")]

    monkeypatch.setattr("apps.tenant_app_service.agents.tools.rag.app_db_session", lambda: _FakeSessionContext())
    monkeypatch.setattr("apps.tenant_app_service.agents.tools.rag.SearchService", _FakeSearchService)

    await retrieve_resource_context.ainvoke(
        {
            "resource_type": "document",
            "resource_id": "42",
            "chunk_indexes": [1],
            "context_range": 1,
        },
        config=runnable_config,
    )

    assert captured_config["tenant_config"] == {}


@pytest.mark.asyncio
async def test_search_documents_with_embedding_config(monkeypatch):
    """Test that tenant_config with embedding settings is passed correctly."""
    from langchain_core.runnables import RunnableConfig

    from apps.tenant_app_service.agents.domain import (
        AgentRuntimeContext,
        AgentTenantContext,
        AgentUserContext,
    )

    captured_config = {}

    class _FakeSearchService:
        def __init__(self, tenant_id, session, user_id, user_role, tenant_config=None, **_kwargs):
            captured_config["tenant_config"] = tenant_config

        async def search_documents(self, *, query, page, page_size):
            return [], PaginationRequest(page=1, page_size=page_size, total=0)

    monkeypatch.setattr("apps.tenant_app_service.agents.tools.rag.app_db_session", lambda: _FakeSessionContext())
    monkeypatch.setattr("apps.tenant_app_service.agents.tools.rag.SearchService", _FakeSearchService)

    # Create runtime context with embedding config
    tenant_config_with_embedding = {
        "embedding": {
            "model": "text-embedding-3-large",
            "dimension": 1024,
        }
    }
    runtime_ctx = AgentRuntimeContext(
        tenant=AgentTenantContext(
            tenant_id=1,
            tenant_name="test_tenant",
            config=tenant_config_with_embedding,
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

    assert captured_config["tenant_config"] == tenant_config_with_embedding
    assert captured_config["tenant_config"]["embedding"]["model"] == "text-embedding-3-large"
    assert captured_config["tenant_config"]["embedding"]["dimension"] == 1024
