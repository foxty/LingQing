"""Tests for document manifest helpers."""

import json
from unittest.mock import AsyncMock

import pytest

from apps.shared.document.manifest import (
    build_blocks_document,
    build_manifest_pointer,
    compute_content_hash,
    extract_text_from_blocks,
    is_manifest_pointer,
    summarize_blocks,
    text_to_blocks,
    try_read_existing_blocks,
)


def test_text_to_blocks_and_summary():
    blocks = text_to_blocks("Hello world")
    doc = build_blocks_document(parser="default", blocks=blocks)
    summary = summarize_blocks(doc["blocks"])
    assert summary["text"] == 1
    assert extract_text_from_blocks(doc) == "Hello world"


def test_manifest_pointer_detection():
    pointer = build_manifest_pointer(
        storage_uri="/tmp/blocks.json",
        content_hash="abc",
        block_summary={"text": 1},
        filename="a.pdf",
        parser="default",
    )
    assert is_manifest_pointer(pointer) is True
    assert is_manifest_pointer({"text": "legacy"}) is False


def test_content_hash_stable():
    doc = build_blocks_document(parser="default", blocks=text_to_blocks("same"))
    assert compute_content_hash(doc) == compute_content_hash(doc)


@pytest.mark.asyncio
async def test_try_read_existing_blocks_returns_none_when_missing():
    storage = AsyncMock()
    storage.exists = AsyncMock(return_value=False)
    result = await try_read_existing_blocks(storage, tenant_id=2, document_id=15)
    assert result is None
    storage.read.assert_not_awaited()


@pytest.mark.asyncio
async def test_persist_parse_images_rewrites_data_uri():
    import base64

    from apps.shared.document.manifest import persist_parse_images

    storage = AsyncMock()
    storage.save = AsyncMock(return_value="stored")
    payload = base64.b64encode(b"png-bytes").decode()
    blocks = [
        {"type": "text", "text": "hi"},
        {"type": "image", "uri": f"data:image/png;base64,{payload}", "caption": "chart"},
        {"type": "image", "uri": "not-an-image"},
    ]

    result = await persist_parse_images(storage, tenant_id=2, document_id=18, blocks=blocks)

    assert result[0]["type"] == "text"
    assert result[1]["uri"].startswith("18/parsed/latest/images/")
    assert result[1]["uri"].endswith(".png")
    assert "data:" not in result[1]["uri"]
    assert len(result) == 2
    storage.save.assert_awaited_once()


def test_document_image_relative_key_rejects_unsafe_names():
    from apps.shared.document.manifest import document_image_relative_key

    assert document_image_relative_key(18, "../blocks.json") is None
    assert document_image_relative_key(18, "not-a-hash.png") is None
    safe_name = "a" * 64 + ".png"
    assert document_image_relative_key(18, safe_name) == f"18/parsed/latest/images/{safe_name}"


@pytest.mark.asyncio
async def test_try_read_existing_blocks_reads_on_disk_document():
    doc = build_blocks_document(parser="docling", blocks=text_to_blocks("sheet one"))
    storage = AsyncMock()
    storage.exists = AsyncMock(return_value=True)
    storage.read = AsyncMock(return_value=json.dumps(doc).encode("utf-8"))
    result = await try_read_existing_blocks(storage, tenant_id=2, document_id=15)
    assert result == doc
