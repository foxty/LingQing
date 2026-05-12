"""Shared markdown → blocks.json IR conversion."""

from __future__ import annotations

import re
from typing import Any

from apps.shared.document.manifest import text_to_blocks
from apps.shared.document.parsers.blocks_common import dedupe_consecutive_headings, normalize_block_text

_SLIDE_NUM_RE = re.compile(r"^\d{1,2}$")


def markdown_to_blocks(markdown: str) -> list[dict[str, Any]]:
    """Convert markdown text to indexable blocks."""
    lines = markdown.splitlines()
    if _looks_like_slide_deck(lines):
        blocks = _slide_deck_markdown_to_blocks(lines)
    else:
        blocks = _standard_markdown_to_blocks(markdown)
    return dedupe_consecutive_headings(blocks)


def _looks_like_slide_deck(lines: list[str]) -> bool:
    stripped = [line.strip() for line in lines if line.strip()]
    if len(stripped) < 6:
        return False
    slide_nums = sum(1 for line in stripped if _SLIDE_NUM_RE.fullmatch(line))
    short_lines = sum(1 for line in stripped if len(line) <= 20)
    return slide_nums >= 2 and short_lines / len(stripped) >= 0.25


def _slide_deck_markdown_to_blocks(lines: list[str]) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    slide_lines: list[str] = []
    table_lines: list[str] = []

    def flush_slide() -> None:
        nonlocal slide_lines
        if not slide_lines:
            return
        text = "\n".join(slide_lines).strip()
        slide_lines = []
        if text:
            blocks.extend(text_to_blocks(text))

    def flush_table() -> None:
        nonlocal table_lines
        if not table_lines:
            return
        blocks.append({"type": "table", "text": "\n".join(table_lines)})
        table_lines = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        if stripped.startswith("#"):
            flush_table()
            flush_slide()
            heading = normalize_block_text(re.sub(r"^#+\s*", "", stripped))
            if heading:
                blocks.append({"type": "heading", "text": heading})
            continue

        if stripped.startswith("|") and stripped.endswith("|"):
            flush_slide()
            table_lines.append(stripped)
            continue

        if stripped.startswith("!["):
            flush_table()
            flush_slide()
            caption_match = re.match(r"!\[(.*?)\]\((.*?)\)", stripped)
            if caption_match:
                blocks.append(
                    {
                        "type": "image",
                        "uri": caption_match.group(2),
                        "caption": caption_match.group(1) or None,
                    }
                )
            continue

        flush_table()
        if _SLIDE_NUM_RE.fullmatch(stripped):
            flush_slide()
            slide_lines.append(stripped)
            continue
        slide_lines.append(stripped)

    flush_table()
    flush_slide()
    return blocks


def _standard_markdown_to_blocks(markdown: str) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    current_heading: str | None = None
    paragraph_lines: list[str] = []
    table_lines: list[str] = []

    def flush_paragraph() -> None:
        nonlocal paragraph_lines
        if not paragraph_lines:
            return
        text = "\n".join(paragraph_lines).strip()
        paragraph_lines = []
        if text:
            blocks.extend(text_to_blocks(text))

    def flush_table() -> None:
        nonlocal table_lines
        if not table_lines:
            return
        blocks.append({"type": "table", "text": "\n".join(table_lines)})
        table_lines = []

    for line in markdown.splitlines():
        stripped = line.strip()
        if not stripped:
            flush_table()
            flush_paragraph()
            continue

        if stripped.startswith("#"):
            flush_table()
            flush_paragraph()
            heading = normalize_block_text(re.sub(r"^#+\s*", "", stripped))
            if heading:
                blocks.append({"type": "heading", "text": heading})
                current_heading = heading
            continue

        if stripped.startswith("|") and stripped.endswith("|"):
            flush_paragraph()
            table_lines.append(stripped)
            continue

        if stripped.startswith("!["):
            flush_table()
            flush_paragraph()
            caption_match = re.match(r"!\[(.*?)\]\((.*?)\)", stripped)
            if caption_match:
                blocks.append(
                    {
                        "type": "image",
                        "uri": caption_match.group(2),
                        "caption": caption_match.group(1) or None,
                    }
                )
            continue

        flush_table()
        paragraph_lines.append(stripped)

    flush_table()
    flush_paragraph()
    if not blocks and markdown.strip():
        blocks.extend(text_to_blocks(markdown))
    if current_heading and len(blocks) == 1 and blocks[0].get("type") == "heading":
        blocks.extend(text_to_blocks(markdown))
    return blocks
