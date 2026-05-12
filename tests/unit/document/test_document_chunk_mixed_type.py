"""Unit tests for document chunk block types."""

from apps.shared.document.schemas import DocumentChunk
from apps.shared.search.search_service import _document_chunk_from_vector


def test_document_chunk_accepts_mixed_block_type():
    chunk = DocumentChunk(chunk_index=0, content="mixed content", block_type="mixed")
    assert chunk.block_type == "mixed"


def test_document_chunk_from_vector_preserves_mixed_block_type():
    document = type(
        "Doc",
        (),
        {
            "page_content": "overview table and text",
            "metadata": {"chunk_index": 3, "block_type": "mixed", "page": 2},
        },
    )()
    chunk = _document_chunk_from_vector(document, relevance=0.8)
    assert chunk.block_type == "mixed"
    assert chunk.page == 2
