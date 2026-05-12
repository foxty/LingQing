"""Tests for block-aware document segmentation."""

import json
from pathlib import Path

import pytest

from apps.shared.document.chunking import (
    _split_markdown_table,
    segment_blocks,
)
from apps.shared.document.manifest import build_blocks_document
from tests.helpers.parsing_quality import assert_fixture_quality, list_unit_fixtures, load_golden_blocks


def test_segment_blocks_merges_heading_with_following_text():
    blocks_doc = build_blocks_document(
        parser="docling",
        blocks=[
            {"type": "heading", "text": "Section Title"},
            {"type": "text", "text": "Body paragraph with enough content to stay meaningful."},
            {"type": "heading", "text": "Next Section"},
            {"type": "text", "text": "Another paragraph."},
        ],
    )

    segments = segment_blocks(blocks_doc, min_chars=1)

    assert len(segments) <= 2
    assert "section title" in segments[0].text.lower()
    assert "body paragraph" in segments[0].text.lower()
    assert all(segment.text.strip() for segment in segments)


def test_segment_blocks_merges_short_text_blocks():
    blocks_doc = build_blocks_document(
        parser="docling",
        blocks=[
            {"type": "text", "text": "Line one"},
            {"type": "text", "text": "Line two"},
            {"type": "text", "text": "Line three"},
        ],
    )

    segments = segment_blocks(blocks_doc, min_chars=80)

    assert len(segments) == 1
    assert "Line one" in segments[0].text
    assert "Line three" in segments[0].text


def test_segment_blocks_indexes_image_caption():
    blocks_doc = build_blocks_document(
        parser="default",
        blocks=[
            {"type": "text", "text": "Intro"},
            {"type": "image", "uri": "18/parsed/latest/images/abc.png", "caption": "Q3 revenue chart", "page": 2},
            {"type": "image", "uri": "18/parsed/latest/images/skip.png"},
            {"type": "table", "text": "| A | B |\n| 1 | 2 |"},
        ],
    )

    segments = segment_blocks(blocks_doc, min_chars=1)
    image_segments = [segment for segment in segments if segment.uri]

    assert len(image_segments) == 1
    assert image_segments[0].uri == "18/parsed/latest/images/abc.png"
    assert image_segments[0].caption == "Q3 revenue chart"
    assert image_segments[0].page == 2
    assert "abc.png" not in image_segments[0].text


def test_segment_blocks_indexes_image_near_label():
    image_uri = "14/parsed/latest/images/" + ("a" * 64) + ".png"
    blocks_doc = build_blocks_document(
        parser="docling",
        blocks=[
            {"type": "text", "text": "Far away", "page": 6, "bbox": {"left": 0, "top": 0, "right": 10, "bottom": 10}},
            {
                "type": "text",
                "text": "Ultra Impact",
                "page": 6,
                "bbox": {"left": 100, "top": 40, "right": 180, "bottom": 55},
            },
            {
                "type": "image",
                "uri": image_uri,
                "page": 6,
                "bbox": {"left": 100, "top": 60, "right": 180, "bottom": 160},
            },
            {
                "type": "text",
                "text": "Other page",
                "page": 7,
                "bbox": {"left": 100, "top": 40, "right": 180, "bottom": 55},
            },
        ],
    )

    segments = segment_blocks(blocks_doc, min_chars=1)
    image_segments = [segment for segment in segments if segment.uri]

    assert len(image_segments) == 1
    assert image_segments[0].text == "Ultra Impact"
    assert image_segments[0].uri == image_uri


def test_segment_blocks_skips_image_with_distant_label():
    blocks_doc = build_blocks_document(
        parser="docling",
        blocks=[
            {"type": "text", "text": "Canvas", "page": 6, "bbox": {"left": 0, "top": 40, "right": 20, "bottom": 55}},
            {
                "type": "image",
                "uri": "14/parsed/latest/images/" + ("b" * 64) + ".png",
                "page": 6,
                "bbox": {"left": 400, "top": 60, "right": 480, "bottom": 160},
            },
        ],
    )

    segments = segment_blocks(blocks_doc, min_chars=1)

    assert not any(segment.uri for segment in segments)


def test_segment_blocks_prefers_caption_over_nearby_label():
    blocks_doc = build_blocks_document(
        parser="docling",
        blocks=[
            {
                "type": "text",
                "text": "Ultra Impact",
                "page": 6,
                "bbox": {"left": 100, "top": 40, "right": 180, "bottom": 55},
            },
            {
                "type": "image",
                "uri": "14/parsed/latest/images/" + ("c" * 64) + ".png",
                "caption": "Product photo",
                "page": 6,
                "bbox": {"left": 100, "top": 60, "right": 180, "bottom": 160},
            },
        ],
    )

    segments = segment_blocks(blocks_doc, min_chars=1)
    image_segments = [segment for segment in segments if segment.uri]

    assert len(image_segments) == 1
    assert image_segments[0].text == "Product photo"
    assert image_segments[0].caption == "Product photo"


def test_segment_blocks_joins_labels_above_and_beside_image():
    blocks_doc = build_blocks_document(
        parser="docling",
        blocks=[
            {
                "type": "text",
                "text": "Black",
                "page": 6,
                "bbox": {"left": 100, "top": 165, "right": 140, "bottom": 175},
            },
            {
                "type": "heading",
                "text": "Canvas",
                "page": 6,
                "bbox": {"left": 10, "top": 60, "right": 70, "bottom": 160},
            },
            {
                "type": "text",
                "text": "Ultra Impact",
                "page": 6,
                "bbox": {"left": 100, "top": 40, "right": 180, "bottom": 55},
            },
            {
                "type": "image",
                "uri": "14/parsed/latest/images/" + ("d" * 64) + ".png",
                "page": 6,
                "bbox": {"left": 100, "top": 60, "right": 180, "bottom": 160},
            },
        ],
    )

    segments = segment_blocks(blocks_doc, min_chars=1)
    image_segments = [segment for segment in segments if segment.uri]

    assert len(image_segments) == 1
    assert image_segments[0].text == "Ultra Impact\n\nCanvas\n\nBlack"


def test_segment_blocks_preserves_page_metadata():
    blocks_doc = build_blocks_document(
        parser="docling",
        blocks=[
            {"type": "heading", "text": "Section Title", "page": 3},
            {"type": "text", "text": "Body paragraph with enough content to stay meaningful.", "page": 3},
        ],
    )

    segments = segment_blocks(blocks_doc, min_chars=1)

    assert len(segments) == 1
    assert segments[0].page == 3


def test_segment_blocks_reduces_heading_only_noise():
    blocks_doc = build_blocks_document(
        parser="docling",
        blocks=[
            {"type": "heading", "text": "Title Only"},
            {"type": "text", "text": "Supporting details for the title."},
        ],
    )

    segments = segment_blocks(blocks_doc, min_chars=1)

    assert len(segments) == 1
    assert "title only" in segments[0].text.lower()
    assert "supporting details" in segments[0].text.lower()


def test_segment_blocks_keeps_whole_table_under_limit():
    table_text = "\n".join(
        [
            "| Month | Interest |",
            "| --- | --- |",
            "| August 2005 | 1354.17 |",
            "| September 2005 | 1350.00 |",
        ]
    )
    blocks_doc = build_blocks_document(parser="docling", blocks=[{"type": "table", "text": table_text}])

    segments = segment_blocks(blocks_doc, min_chars=1)

    assert len(segments) == 1
    assert "August 2005" in segments[0].text
    assert segments[0].kind == "table"


def test_segment_blocks_splits_large_table_on_row_boundaries():
    rows = ["| Month | Interest |", "| --- | --- |"]
    rows.extend(f"| Month {index} | {1000 + index}.00 |" for index in range(1, 80))
    table_text = "\n".join(rows)

    parts = _split_markdown_table(table_text, max_chars=512)

    assert len(parts) > 1
    for part in parts:
        assert part.startswith("| Month | Interest |")
        assert "| --- | --- |" in part
        assert part.count("\n") >= 2


def test_segment_blocks_coalesces_table_heavy_mortgage_fixture():
    baseline_path = Path("tests/fixtures/parsing/baselines/mortgage_pdf.blocks.golden.json")
    blocks_doc = json.loads(baseline_path.read_text())

    segments = segment_blocks(blocks_doc)

    assert len(segments) <= 30
    table_segments = [segment for segment in segments if segment.kind in {"table", "mixed"}]
    assert table_segments
    assert all("Month" in segment.text or "Loan amount" in segment.text for segment in table_segments[:3])


@pytest.mark.parametrize("fixture", list_unit_fixtures(), ids=lambda item: item["id"])
def test_golden_blocks_meet_chunk_quality_thresholds(fixture):
    golden = load_golden_blocks(fixture["golden_blocks"])
    assert_fixture_quality(golden, fixture["quality"])
