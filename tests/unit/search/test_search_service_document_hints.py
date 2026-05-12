"""Tests for document search hints and batch context retrieval."""

from unittest.mock import AsyncMock

import pytest
from langchain_core.documents import Document

from apps.shared.document.schemas import DocumentChunk, DocumentSearchResult
from apps.shared.domain.types import RESOURCE_TYPE_DOCUMENT
from apps.shared.search.schemas import ResourceContextChunk
from apps.shared.search.search_service import SearchService, finalize_document_context_chunk


def test_document_to_item_limits_chunk_hints_and_adds_section_hint():
    service = SearchService.__new__(SearchService)
    result = DocumentSearchResult(
        doc_id=14,
        collection_id=3,
        filename="workshop.pptx",
        chunks=[
            DocumentChunk(chunk_index=21, content="launch dates and channel limits", relevance=0.2),
            DocumentChunk(chunk_index=2, content="product overview iphone 18 franchise overview", relevance=0.9),
            DocumentChunk(chunk_index=8, content="canvas ultra impact magsafe assortment", relevance=0.7),
            DocumentChunk(chunk_index=11, content="d2c iphone 18 pro skus", relevance=0.6),
            DocumentChunk(chunk_index=2, content="duplicate chunk index", relevance=0.1),
        ],
    )

    item = service._document_to_item(result)

    assert len(item.contents) == 3
    assert all(entry["collection_id"] == 3 for entry in item.contents)
    assert [entry["chunk_index"] for entry in item.contents] == [2, 8, 11]
    assert item.contents[0]["section_hint"].startswith("product overview iphone 18")


def test_finalize_document_context_chunk_adds_public_image_fields():
    image_name = "a" * 64 + ".png"
    chunk = ResourceContextChunk(
        chunk_index=166,
        total_chunks=566,
        content="Black on Black\n\nAlloy Ripple",
        block_type="image",
        image_uri=f"14/parsed/latest/images/{image_name}",
        page=6,
    )

    finalized = finalize_document_context_chunk(chunk, 14)

    image_url = f"/documents/14/images/{image_name}"
    assert finalized.image_url == image_url
    assert finalized.image_markdown == f"![Black on Black\n\nAlloy Ripple]({image_url})"
    payload = finalized.model_dump(mode="json")
    assert "image_uri" not in payload
    assert payload["image_url"] == image_url


def test_document_to_item_includes_page_and_image_url():
    service = SearchService.__new__(SearchService)
    image_uri = "14/parsed/latest/images/" + ("a" * 64) + ".png"
    result = DocumentSearchResult(
        doc_id=14,
        collection_id=3,
        filename="workshop.pptx",
        chunks=[
            DocumentChunk(
                chunk_index=166,
                content="black on black alloy ripple",
                relevance=0.9,
                page=6,
                block_type="image",
                image_uri=image_uri,
            ),
        ],
    )

    item = service._document_to_item(result)

    assert item.contents[0]["page"] == 6
    assert item.contents[0]["block_type"] == "image"
    assert item.contents[0]["image_url"] == f"/documents/14/images/{'a' * 64}.png"


def test_normalize_context_anchors_deduplicates_and_caps():
    anchors = SearchService._normalize_context_anchors([2, 2, 8, 11, 19, 78])

    assert anchors == [2, 8, 11]


@pytest.mark.asyncio
async def test_get_resource_context_chunks_for_anchors_merges_and_deduplicates():
    service = SearchService.__new__(SearchService)
    service.user_id = None
    service._authorize_resource_context = AsyncMock()
    service._fetch_context_docs = AsyncMock(
        side_effect=[
            [
                Document(page_content="chunk-1", metadata={"chunk_index": 1, "total_chunks": 10}),
                Document(page_content="chunk-2", metadata={"chunk_index": 2, "total_chunks": 10}),
                Document(page_content="chunk-3", metadata={"chunk_index": 3, "total_chunks": 10}),
            ],
            [
                Document(page_content="chunk-3-dup", metadata={"chunk_index": 3, "total_chunks": 10}),
                Document(page_content="chunk-8", metadata={"chunk_index": 8, "total_chunks": 10}),
            ],
        ]
    )

    chunks = await service.get_resource_context_chunks_for_anchors(
        resource_type=RESOURCE_TYPE_DOCUMENT,
        resource_id=14,
        chunk_indexes=[2, 8],
        context_range=2,
    )

    assert [chunk.chunk_index for chunk in chunks] == [1, 2, 3, 8]
    assert chunks[2].content == "chunk-3"
    service._authorize_resource_context.assert_awaited_once()


@pytest.mark.asyncio
async def test_fetch_context_docs_merges_page_siblings():
    service = SearchService.__new__(SearchService)
    service.rag_manager = AsyncMock()
    service.rag_manager.get_context_chunks_by_resource = AsyncMock(
        return_value=[
            Document(page_content="anchor", metadata={"chunk_index": 165, "page": 6}),
            Document(page_content="neighbor", metadata={"chunk_index": 166, "page": 6}),
        ]
    )
    service.rag_manager.get_chunks_by_page = AsyncMock(
        return_value=[
            Document(page_content="anchor", metadata={"chunk_index": 165, "page": 6}),
            Document(page_content="neighbor", metadata={"chunk_index": 166, "page": 6}),
            Document(page_content="same page", metadata={"chunk_index": 170, "page": 6}),
        ]
    )

    docs = await service._fetch_context_docs(
        resource_type=RESOURCE_TYPE_DOCUMENT,
        resource_id=14,
        chunk_index=165,
        context_range=1,
    )

    assert [doc.metadata["chunk_index"] for doc in docs] == [165, 166, 170]
    service.rag_manager.get_chunks_by_page.assert_awaited_once_with(
        resource_type=RESOURCE_TYPE_DOCUMENT,
        resource_id=14,
        page=6,
        limit=200,
    )
