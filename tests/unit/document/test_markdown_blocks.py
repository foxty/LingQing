"""Tests for shared markdown → blocks conversion."""

from apps.shared.document.parsers.markdown_blocks import markdown_to_blocks


def test_markdown_to_blocks_handles_mixed_content():
    markdown = "# Heading\n\nParagraph one.\n\n| A | B |\n| --- | --- |\n| 1 | 2 |"
    blocks = markdown_to_blocks(markdown)
    types = {block["type"] for block in blocks}
    assert "heading" in types
    assert "table" in types
    table_blocks = [block for block in blocks if block["type"] == "table"]
    assert len(table_blocks) == 1
    assert "| --- | --- |" in table_blocks[0]["text"]


def test_markdown_to_blocks_groups_slide_deck_lines():
    markdown = "\n".join(
        [
            "01",
            "Intro",
            "Short line",
            "02",
            "Goals",
            "Another line",
            "03",
            "Summary",
            "Final line",
            "04",
            "Thanks",
            "End slide",
        ]
    )
    blocks = markdown_to_blocks(markdown)
    text_blocks = [block for block in blocks if block["type"] == "text"]
    assert len(text_blocks) == 4
    assert "01" in text_blocks[0]["text"]
    assert "Goals" in text_blocks[1]["text"]


def test_markdown_to_blocks_dedupes_consecutive_headings():
    markdown = "# Same Title\n\n# Same Title\n\nBody paragraph."
    blocks = markdown_to_blocks(markdown)
    headings = [block for block in blocks if block["type"] == "heading"]
    assert len(headings) == 1
    assert headings[0]["text"] == "Same Title"


def test_markdown_to_blocks_strips_bold_markers_from_headings():
    markdown = "# **Bold Title**\n\nParagraph."
    blocks = markdown_to_blocks(markdown)
    headings = [block for block in blocks if block["type"] == "heading"]
    assert headings[0]["text"] == "Bold Title"


def test_markdown_to_blocks_handles_image_and_heading_only_fallback():
    markdown = "# Only Heading"
    blocks = markdown_to_blocks(markdown)
    assert any(block["type"] == "heading" for block in blocks)
    assert any(block["type"] == "text" for block in blocks)

    image_md = "![chart](images/chart.png)"
    image_blocks = markdown_to_blocks(image_md)
    assert image_blocks[0]["type"] == "image"
    assert image_blocks[0]["uri"] == "images/chart.png"
