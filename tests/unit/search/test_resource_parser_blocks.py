"""Tests for block-aware resource parser."""

from apps.shared.document.manifest import build_blocks_document, build_manifest_pointer
from apps.shared.domain.types import RESOURCE_TYPE_DOCUMENT
from apps.shared.search.parser import ResourceParser, extract_text_from_raw


def test_resource_parser_uses_env_chunk_settings(monkeypatch):
    monkeypatch.setattr("apps.shared.search.parser.resource_parser.apps.config.EnvConfig.DOCUMENT_CHUNK_SIZE", 256)
    monkeypatch.setattr("apps.shared.search.parser.resource_parser.apps.config.EnvConfig.DOCUMENT_CHUNK_OVERLAP", 32)
    monkeypatch.setattr(
        "apps.shared.search.parser.resource_parser.apps.config.EnvConfig.DOCUMENT_CHUNK_MIN_CHARS",
        40,
    )
    monkeypatch.setattr(
        "apps.shared.search.parser.resource_parser.apps.config.EnvConfig.DOCUMENT_TABLE_MAX_CHARS",
        1500,
    )

    parser = ResourceParser()

    assert parser._chunk_size == 256
    assert parser._chunk_overlap == 32
    assert parser._min_chars == 40
    assert parser._table_max_chars == 1500


def test_extract_text_legacy_inline():
    raw = {"text": "legacy body", "meta": {"filename": "a.txt"}}
    assert extract_text_from_raw(raw) == "legacy body"


def test_extract_text_from_raw_skips_manifest_pointer():
    pointer = build_manifest_pointer(
        storage_uri="/tmp/blocks.json",
        content_hash="hash",
        block_summary={"text": 1},
        filename="report.pdf",
        parser="docling",
    )

    assert extract_text_from_raw(pointer) == ""


def test_from_raw_tokenizes_blocks_document_text():
    blocks_doc = build_blocks_document(
        parser="docling",
        blocks=[
            {"type": "heading", "text": "Revenue Overview"},
            {"type": "text", "text": "North region grew twelve percent."},
        ],
    )
    pointer = build_manifest_pointer(
        storage_uri="/tmp/blocks.json",
        content_hash="hash",
        block_summary={"heading": 1, "text": 1},
        filename="report.pdf",
        parser="docling",
    )
    parser = ResourceParser()

    result = parser.from_raw(
        pointer,
        RESOURCE_TYPE_DOCUMENT,
        source_parser="docling",
        blocks_document=blocks_doc,
    )

    assert "north" in result.tokenized_content
    assert "revenu" in result.tokenized_content
    assert "overview" in result.tokenized_content


def test_chunk_blocks_document_marks_table_metadata():
    blocks_doc = build_blocks_document(
        parser="docling",
        blocks=[
            {"type": "table", "text": "| Region | Revenue |\n| --- | --- | \n| North | 120 |"},
        ],
    )
    pointer = build_manifest_pointer(
        storage_uri="/tmp/blocks.json",
        content_hash="hash",
        block_summary={"table": 1},
        filename="report.pdf",
        parser="docling",
    )
    parser = ResourceParser()

    result = parser.from_raw(
        pointer,
        RESOURCE_TYPE_DOCUMENT,
        source_parser="docling",
        blocks_document=blocks_doc,
    )

    assert result.chunks
    assert all(chunk.metadata.get("block_type") == "table" for chunk in result.chunks)


def test_from_raw_splits_long_inline_document_text():
    parser = ResourceParser(chunk_size=128, chunk_overlap=16, min_chars=1)
    raw_content = {
        "text": " ".join(f"segment-{index}" for index in range(80)),
        "meta": {"filename": "long.txt"},
    }

    result = parser.from_raw(raw_content, RESOURCE_TYPE_DOCUMENT)

    assert len(result.chunks) > 1
    assert all(chunk.metadata.get("chunk_index") is not None for chunk in result.chunks)


def test_chunk_blocks_document_indexes_image_caption():
    image_uri = "18/parsed/latest/images/abc.png"
    blocks_doc = build_blocks_document(
        parser="default",
        blocks=[
            {"type": "text", "text": "Intro paragraph"},
            {"type": "image", "uri": image_uri, "caption": "Q3 revenue chart", "page": 4},
            {"type": "table", "text": "| A | B |"},
        ],
    )
    pointer = build_manifest_pointer(
        storage_uri="/tmp/blocks.json",
        content_hash="hash",
        block_summary={"text": 1, "table": 1, "image": 1},
        filename="report.pdf",
        parser="default",
    )
    parser = ResourceParser()
    result = parser.from_raw(
        pointer,
        RESOURCE_TYPE_DOCUMENT,
        source_parser="default",
        blocks_document=blocks_doc,
    )
    assert "intro paragraph" in result.tokenized_content
    image_chunks = [chunk for chunk in result.chunks if chunk.metadata.get("block_type") == "image"]
    assert len(image_chunks) == 1
    assert image_chunks[0].metadata["image_uri"] == image_uri
    assert image_chunks[0].metadata["page"] == 4
    assert "q3 revenue chart" in image_chunks[0].page_content


def test_chunk_blocks_document_indexes_image_near_label():
    image_uri = "14/parsed/latest/images/" + ("e" * 64) + ".png"
    blocks_doc = build_blocks_document(
        parser="docling",
        blocks=[
            {
                "type": "text",
                "text": "Volume Engine",
                "page": 2,
                "bbox": {"left": 200, "top": 40, "right": 280, "bottom": 120},
            },
            {
                "type": "image",
                "uri": image_uri,
                "page": 2,
                "bbox": {"left": 100, "top": 40, "right": 180, "bottom": 120},
            },
        ],
    )
    pointer = build_manifest_pointer(
        storage_uri="/tmp/blocks.json",
        content_hash="hash",
        block_summary={"text": 1, "image": 1},
        filename="lanes.pptx",
        parser="docling",
    )
    parser = ResourceParser(min_chars=1)
    result = parser.from_raw(
        pointer,
        RESOURCE_TYPE_DOCUMENT,
        source_parser="docling",
        blocks_document=blocks_doc,
    )

    image_chunks = [chunk for chunk in result.chunks if chunk.metadata.get("block_type") == "image"]
    assert len(image_chunks) == 1
    assert image_chunks[0].metadata["image_uri"] == image_uri
    assert "volume engine" in image_chunks[0].page_content


def test_chunk_blocks_document_preserves_page_metadata():
    blocks_doc = build_blocks_document(
        parser="docling",
        blocks=[
            {"type": "heading", "text": "Section Title", "page": 2},
            {"type": "text", "text": "Body paragraph with enough content to stay meaningful.", "page": 2},
        ],
    )
    pointer = build_manifest_pointer(
        storage_uri="/tmp/blocks.json",
        content_hash="hash",
        block_summary={"heading": 1, "text": 1},
        filename="report.pdf",
        parser="docling",
    )
    parser = ResourceParser()
    result = parser.from_raw(
        pointer,
        RESOURCE_TYPE_DOCUMENT,
        source_parser="docling",
        blocks_document=blocks_doc,
    )

    assert result.chunks
    assert all(chunk.metadata.get("page") == 2 for chunk in result.chunks)
