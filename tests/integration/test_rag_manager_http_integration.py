"""Integration tests for RAGManager against Chroma HTTP mode."""

import asyncio
import time
import uuid

import pytest
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings

from apps.shared.data_source.schemas import RAGSourceType
from apps.shared.infra.rag.rag_manager import RAGManager

pytestmark = pytest.mark.asyncio


class KeywordEmbeddings(Embeddings):
    """Deterministic keyword-count embeddings for integration tests."""

    _keywords = [
        "alpha",
        "beta",
        "tenant1",
        "tenant2",
        "document",
        "asset",
        "shared",
    ]

    def _encode(self, text: str) -> list[float]:
        lowered = text.lower()
        return [float(lowered.count(keyword)) for keyword in self._keywords]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._encode(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._encode(text)


@pytest.fixture
def configure_http_chroma(monkeypatch, chroma_http_endpoint):
    """Patch EnvConfig for HTTP mode with an isolated collection prefix."""

    host, port = chroma_http_endpoint
    prefix = f"it_{uuid.uuid4().hex}_tenant_"

    monkeypatch.setattr("apps.shared.infra.rag.chroma_backend.EnvConfig.CHROMA_MODE", "http")
    monkeypatch.setattr("apps.shared.infra.rag.chroma_backend.EnvConfig.CHROMA_URL", f"http://{host}:{port}")
    monkeypatch.setattr("apps.shared.infra.rag.chroma_backend.EnvConfig.CHROMA_COLLECTION_PREFIX", prefix)

    return KeywordEmbeddings()


async def _wait_until(assertion_coro, timeout_seconds: float = 8.0) -> None:
    """Retry assertion coroutine until it passes or timeout is reached."""

    deadline = time.monotonic() + timeout_seconds
    last_error = None
    while time.monotonic() < deadline:
        try:
            await assertion_coro()
            return
        except AssertionError as exc:
            last_error = exc
            await asyncio.sleep(0.2)

    if last_error is not None:
        raise last_error
    raise AssertionError("Condition was not met before timeout")


async def test_http_mode_add_get_search_delete_round_trip(configure_http_chroma):
    """Verify add/get/retrieve/context/delete behavior end-to-end on Chroma HTTP."""

    manager = RAGManager(tenant_id=101, embeddings=configure_http_chroma)

    chunks = [
        Document(
            page_content="alpha document shared section 0",
            metadata={
                "tenant_id": 101,
                "resource_id": 123,
                "resource_type": RAGSourceType.DOCUMENT.value,
                "chunk_index": 0,
            },
        ),
        Document(
            page_content="alpha document shared section 1",
            metadata={
                "tenant_id": 101,
                "resource_id": 123,
                "resource_type": RAGSourceType.DOCUMENT.value,
                "chunk_index": 1,
            },
        ),
        Document(
            page_content="beta document shared section 2",
            metadata={
                "tenant_id": 101,
                "resource_id": 123,
                "resource_type": RAGSourceType.DOCUMENT.value,
                "chunk_index": 2,
            },
        ),
    ]

    assert await manager.add_chunks(chunks) == 3

    async def assert_written():
        by_ref = await manager.get_chunks_by_resource(resource_type=RAGSourceType.DOCUMENT.value, resource_id=123)
        assert len(by_ref) == 3

    await _wait_until(assert_written)

    searched = await manager.retrieve(query="alpha shared", k=2, resource_types=[RAGSourceType.DOCUMENT.value])
    assert len(searched) == 2
    assert all(doc.metadata.get("tenant_id") == 101 for doc in searched)
    assert all(doc.metadata.get("resource_type") == RAGSourceType.DOCUMENT.value for doc in searched)

    context_docs = await manager.get_context_chunks_by_resource(
        resource_type=RAGSourceType.DOCUMENT.value, resource_id=123, chunk_index=1, context_range=1
    )
    assert [doc.metadata.get("chunk_index") for doc in context_docs] == [0, 1, 2]

    assert await manager.remove_by_resource(resource_type=RAGSourceType.DOCUMENT.value, resource_id=123) is True

    async def assert_deleted():
        by_ref_after_delete = await manager.get_chunks_by_resource(
            resource_type=RAGSourceType.DOCUMENT.value, resource_id=123
        )
        assert by_ref_after_delete == []

    await _wait_until(assert_deleted)


async def test_http_mode_multi_tenant_isolation(configure_http_chroma):
    """Verify data is isolated across tenants for retrieve and get_by_ref_id."""

    embeddings = configure_http_chroma
    manager_tenant_1 = RAGManager(tenant_id=201, embeddings=embeddings)
    manager_tenant_2 = RAGManager(tenant_id=202, embeddings=embeddings)

    shared_res_id = 111

    await manager_tenant_1.add_chunks(
        [
            Document(
                page_content="alpha tenant1 private content",
                metadata={
                    "tenant_id": 201,
                    "resource_type": RAGSourceType.DOCUMENT.value,
                    "resource_id": shared_res_id,
                    "chunk_index": 0,
                },
            )
        ]
    )

    await manager_tenant_2.add_chunks(
        [
            Document(
                page_content="beta tenant2 private content",
                metadata={
                    "tenant_id": 202,
                    "resource_type": RAGSourceType.DOCUMENT.value,
                    "resource_id": shared_res_id,
                    "chunk_index": 0,
                },
            )
        ]
    )

    async def assert_isolated_get_by_ref():
        tenant_1_docs = await manager_tenant_1.get_chunks_by_resource(
            resource_type=RAGSourceType.DOCUMENT.value, resource_id=shared_res_id
        )
        tenant_2_docs = await manager_tenant_2.get_chunks_by_resource(
            resource_type=RAGSourceType.DOCUMENT.value, resource_id=shared_res_id
        )

        assert len(tenant_1_docs) == 1
        assert len(tenant_2_docs) == 1
        assert tenant_1_docs[0].metadata["tenant_id"] == 201
        assert tenant_2_docs[0].metadata["tenant_id"] == 202

    await _wait_until(assert_isolated_get_by_ref)

    tenant_1_search = await manager_tenant_1.retrieve(query="tenant2 beta", k=3)
    tenant_2_search = await manager_tenant_2.retrieve(query="tenant1 alpha", k=3)

    assert all(doc.metadata.get("tenant_id") == 201 for doc in tenant_1_search)
    assert all(doc.metadata.get("tenant_id") == 202 for doc in tenant_2_search)
    assert all("tenant2 private" not in doc.page_content for doc in tenant_1_search)
    assert all("tenant1 private" not in doc.page_content for doc in tenant_2_search)


async def test_http_mode_retrieve_honors_resource_type_filter(configure_http_chroma):
    """Verify retrieve(resource_types=...) only returns matching resource types."""

    manager = RAGManager(tenant_id=303, embeddings=configure_http_chroma)

    await manager.add_chunks(
        [
            Document(
                page_content="alpha document payload",
                metadata={
                    "tenant_id": 303,
                    "resource_id": 1,
                    "resource_type": RAGSourceType.DOCUMENT.value,
                    "chunk_index": 0,
                },
            ),
            Document(
                page_content="alpha asset payload",
                metadata={
                    "tenant_id": 303,
                    "resource_id": 2,
                    "resource_type": RAGSourceType.ASSET.value,
                    "chunk_index": 0,
                },
            ),
        ]
    )

    async def assert_both_types_present():
        all_docs = await manager.retrieve(query="alpha", k=5)
        resource_types = {doc.metadata.get("resource_type") for doc in all_docs}
        assert RAGSourceType.DOCUMENT.value in resource_types
        assert RAGSourceType.ASSET.value in resource_types

    await _wait_until(assert_both_types_present)

    doc_only = await manager.retrieve(query="alpha", k=5, resource_types=[RAGSourceType.DOCUMENT.value])
    asset_only = await manager.retrieve(query="alpha", k=5, resource_types=[RAGSourceType.ASSET.value])

    assert doc_only
    assert asset_only
    assert all(doc.metadata.get("resource_type") == RAGSourceType.DOCUMENT.value for doc in doc_only)
    assert all(doc.metadata.get("resource_type") == RAGSourceType.ASSET.value for doc in asset_only)
