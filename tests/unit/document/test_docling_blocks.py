"""Tests for Docling JSON to blocks mapping."""

from apps.shared.document.parsers.blocks_common import dedupe_consecutive_headings
from apps.shared.document.parsers.docling import _blocks_from_payload, _extract_json_content
from apps.shared.document.parsers.docling_blocks import (
    docling_json_to_blocks,
    supplement_tables_from_markdown,
)


def test_docling_json_to_blocks_maps_labels_and_pages():
    json_content = {
        "texts": [
            {
                "text": "Quarterly Report",
                "label": "title",
                "prov": [{"page_no": 1}],
            },
            {
                "text": "Revenue grew 12%.",
                "label": "paragraph",
                "prov": [{"page_no": 1}],
            },
        ],
        "tables": [
            {
                "text": "| Region | Q1 |\n| --- | --- |",
                "prov": [{"page_no": 2}],
            }
        ],
        "pictures": [
            {
                "uri": "images/chart.png",
                "caption": "Growth chart",
                "prov": [{"page_no": 2}],
            }
        ],
    }
    blocks = docling_json_to_blocks(json_content)
    assert blocks is not None
    assert blocks[0] == {"type": "heading", "text": "Quarterly Report", "page": 1}
    assert blocks[1]["type"] == "text"
    assert blocks[2]["type"] == "table"
    assert blocks[2]["page"] == 2
    assert blocks[3]["type"] == "image"
    assert blocks[3]["uri"] == "images/chart.png"


def test_docling_json_to_blocks_normalizes_bottomleft_bbox():
    json_content = {
        "pages": {"2": {"page_no": 2, "size": {"width": 200, "height": 100}}},
        "texts": [
            {
                "text": "Ultra Impact",
                "label": "paragraph",
                "prov": [
                    {
                        "page_no": 2,
                        "bbox": {"l": 10, "t": 80, "r": 40, "b": 70, "coord_origin": "BOTTOMLEFT"},
                    }
                ],
            }
        ],
        "pictures": [
            {
                "image": {"uri": "data:image/png;base64,abc"},
                "prov": [
                    {
                        "page_no": 2,
                        "bbox": {"l": 10, "t": 60, "r": 40, "b": 20, "coord_origin": "BOTTOMLEFT"},
                    }
                ],
            }
        ],
    }

    blocks = docling_json_to_blocks(json_content)

    assert blocks is not None
    assert blocks[0]["bbox"] == {"left": 10.0, "top": 20.0, "right": 40.0, "bottom": 30.0}
    assert blocks[1]["bbox"] == {"left": 10.0, "top": 40.0, "right": 40.0, "bottom": 80.0}


def test_docling_json_to_blocks_keeps_topleft_bbox_on_text_and_table():
    json_content = {
        "texts": [
            {
                "text": "Canvas",
                "label": "section_header",
                "prov": [{"page_no": 1, "bbox": {"l": 1, "t": 2, "r": 30, "b": 12, "coord_origin": "TOPLEFT"}}],
            }
        ],
        "tables": [
            {
                "text": "| A | B |",
                "prov": [{"page_no": 1, "bbox": {"l": 5, "t": 40, "r": 90, "b": 80}}],
            }
        ],
    }

    blocks = docling_json_to_blocks(json_content)

    assert blocks is not None
    assert blocks[0]["type"] == "heading"
    assert blocks[0]["bbox"] == {"left": 1.0, "top": 2.0, "right": 30.0, "bottom": 12.0}
    assert blocks[1]["bbox"] == {"left": 5.0, "top": 40.0, "right": 90.0, "bottom": 80.0}


def test_docling_json_to_blocks_omits_bbox_when_bottomleft_has_no_page_size():
    json_content = {
        "texts": [
            {
                "text": "Volume Engine",
                "label": "paragraph",
                "prov": [
                    {
                        "page_no": 3,
                        "bbox": {"l": 10, "t": 80, "r": 40, "b": 70, "coord_origin": "BOTTOMLEFT"},
                    }
                ],
            }
        ],
    }

    blocks = docling_json_to_blocks(json_content)

    assert blocks is not None
    assert blocks[0]["page"] == 3
    assert "bbox" not in blocks[0]


def test_docling_json_to_blocks_returns_none_for_unsupported_payload():
    assert docling_json_to_blocks({}) is None
    assert docling_json_to_blocks({"texts": []}) is None


def test_extract_json_content_reads_nested_document_shapes():
    payload = {
        "documents": [
            {
                "json_content": {
                    "texts": [{"text": "Body", "label": "paragraph"}],
                }
            }
        ]
    }
    assert _extract_json_content(payload)["texts"][0]["text"] == "Body"


def test_blocks_from_payload_prefers_json_over_markdown():
    payload = {
        "markdown": "# Title\n\nIgnored when JSON is present.",
        "document": {
            "texts": [
                {"text": "From JSON", "label": "paragraph"},
            ]
        },
    }
    blocks = _blocks_from_payload(payload)
    assert blocks is not None
    assert blocks[0]["text"] == "From JSON"


def test_docling_json_to_blocks_extracts_table_from_grid_cells():
    json_content = {
        "texts": [{"text": "Mortgage overview", "label": "section_header"}],
        "tables": [
            {
                "data": {
                    "num_rows": 2,
                    "num_cols": 2,
                    "table_cells": [
                        {"text": "Month", "start_row_offset_idx": 0, "start_col_offset_idx": 0},
                        {"text": "Interest", "start_row_offset_idx": 0, "start_col_offset_idx": 1},
                        {"text": "August 2005", "start_row_offset_idx": 1, "start_col_offset_idx": 0},
                        {"text": "1354.17", "start_row_offset_idx": 1, "start_col_offset_idx": 1},
                    ],
                }
            }
        ],
    }
    blocks = docling_json_to_blocks(json_content)
    assert blocks is not None
    table_blocks = [block for block in blocks if block["type"] == "table"]
    assert len(table_blocks) == 1
    assert "Month" in table_blocks[0]["text"]
    assert "August 2005" in table_blocks[0]["text"]


def test_supplement_tables_from_markdown_appends_missing_table():
    json_blocks = [
        {"type": "heading", "text": "Revenue Overview"},
        {"type": "text", "text": "Intro paragraph."},
    ]
    markdown = "\n".join(
        [
            "## Revenue Overview",
            "",
            "| Region | Revenue |",
            "| --- | --- |",
            "| North | 120 |",
        ]
    )
    blocks = supplement_tables_from_markdown(json_blocks, markdown)
    assert any(block["type"] == "table" for block in blocks)
    assert any("North" in block.get("text", "") for block in blocks)


def test_blocks_from_payload_supplements_tables_from_markdown():
    payload = {
        "markdown": "| Region | Revenue |\n| --- | --- |\n| North | 120 |",
        "document": {
            "texts": [
                {"text": "Quarterly Report", "label": "title"},
                {"text": "Intro paragraph.", "label": "paragraph"},
            ]
        },
    }
    blocks = _blocks_from_payload(payload)
    assert blocks is not None
    assert any(block["type"] == "table" for block in blocks)
    assert any("North" in block.get("text", "") for block in blocks)


def test_supplement_tables_from_markdown_skips_when_json_already_has_table():
    json_blocks = [
        {"type": "text", "text": "Intro"},
        {"type": "table", "text": "| Region | Revenue |\n| --- | --- |\n| North | 120 |"},
    ]
    markdown = "| Region | Revenue |\n| --- | --- |\n| North | 120 |"

    blocks = supplement_tables_from_markdown(json_blocks, markdown)

    assert [block["type"] for block in blocks].count("table") == 1


def test_supplement_tables_from_markdown_skips_duplicate_table_text():
    json_blocks = [
        {"type": "text", "text": "| Region | Revenue |\n| --- | --- |\n| North | 120 |"},
    ]
    markdown = "| Region | Revenue |\n| --- | --- |\n| North | 120 |"

    blocks = supplement_tables_from_markdown(json_blocks, markdown)

    assert [block["type"] for block in blocks].count("table") == 0
    assert len(blocks) == 1


def test_dedupe_consecutive_headings():
    blocks = [
        {"type": "heading", "text": "Same"},
        {"type": "heading", "text": "Same"},
        {"type": "text", "text": "Body"},
    ]
    deduped = dedupe_consecutive_headings(blocks)
    assert len(deduped) == 2
    assert deduped[0]["type"] == "heading"
    assert deduped[1]["type"] == "text"
