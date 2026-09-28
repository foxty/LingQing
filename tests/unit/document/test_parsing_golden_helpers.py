"""Tests for parsing golden block comparison helpers."""

import pytest

from tests.helpers.parsing_quality import (
    DOCLING_VERSION_FILE,
    GOLDEN_DOCUMENT_ID,
    blocks_match_golden,
    golden_blocks_diff,
    normalize_blocks_document,
    persist_integration_blocks,
    pinned_docling_image,
)


def test_pinned_docling_image_matches_deploy_pin():
    expected = DOCLING_VERSION_FILE.read_text(encoding="utf-8").strip()
    assert pinned_docling_image() == expected


def test_blocks_match_golden_requires_full_block_shape():
    golden = {
        "schema_version": 1,
        "parser": "docling",
        "blocks": [{"type": "text", "text": "Body", "page": 2}],
    }
    actual = {
        "schema_version": 1,
        "parser": "docling",
        "blocks": [{"type": "text", "text": "Body", "page": 2}],
    }
    assert blocks_match_golden(actual, golden)


def test_blocks_match_golden_ignores_small_bbox_differences():
    golden = {
        "schema_version": 1,
        "parser": "docling",
        "blocks": [
            {
                "type": "text",
                "text": "Body",
                "page": 1,
                "bbox": {"left": 1.004, "top": 2.004, "right": 3.004, "bottom": 4.004},
            }
        ],
    }
    actual = {
        "schema_version": 1,
        "parser": "docling",
        "blocks": [
            {
                "type": "text",
                "text": "Body",
                "page": 1,
                "bbox": {"left": 1.001, "top": 2.001, "right": 3.001, "bottom": 4.001},
            }
        ],
    }
    assert blocks_match_golden(actual, golden)


def test_golden_blocks_diff_reports_first_mismatch():
    golden = {
        "schema_version": 1,
        "parser": "docling",
        "blocks": [{"type": "text", "text": "Expected", "page": 1}],
    }
    actual = {
        "schema_version": 1,
        "parser": "docling",
        "blocks": [{"type": "text", "text": "Actual", "page": 1}],
    }
    diff = golden_blocks_diff(actual, golden)
    assert "block[0]" in diff
    assert "text:" in diff


def test_blocks_match_golden_detects_image_uri_differences():
    golden = {
        "schema_version": 1,
        "parser": "docling",
        "blocks": [
            {
                "type": "image",
                "uri": f"{GOLDEN_DOCUMENT_ID}/parsed/latest/images/" + "a" * 64 + ".png",
                "caption": None,
                "page": 1,
            }
        ],
    }
    actual = {
        "schema_version": 1,
        "parser": "docling",
        "blocks": [
            {
                "type": "image",
                "uri": "data:image/png;base64,abc",
                "caption": None,
                "page": 1,
            }
        ],
    }
    assert not blocks_match_golden(actual, golden)


def test_normalize_blocks_document_preserves_persisted_image_fields():
    document = {
        "schema_version": 1,
        "parser": "docling",
        "blocks": [
            {
                "type": "image",
                "uri": f"{GOLDEN_DOCUMENT_ID}/parsed/latest/images/" + "b" * 64 + ".png",
                "caption": None,
                "page": 1,
                "bbox": {"left": 1.0, "top": 2.0, "right": 3.0, "bottom": 4.0},
            },
        ],
    }
    normalized = normalize_blocks_document(document)
    assert normalized["blocks"] == document["blocks"]


@pytest.mark.asyncio
async def test_persist_integration_blocks_rewrites_data_uri(tmp_path, monkeypatch):
    import base64

    monkeypatch.setattr("apps.config.EnvConfig.DATA_ROOT_PATH", str(tmp_path))

    payload = base64.b64encode(b"png-bytes").decode()
    document = {
        "schema_version": 1,
        "parser": "docling",
        "blocks": [
            {"type": "image", "uri": f"data:image/png;base64,{payload}", "caption": None, "page": 1},
        ],
    }

    persisted = await persist_integration_blocks(document)

    image = persisted["blocks"][0]
    assert image["uri"].startswith(f"{GOLDEN_DOCUMENT_ID}/parsed/latest/images/")
    assert image["uri"].endswith(".png")
    assert image["caption"] is None
    assert image["page"] == 1
