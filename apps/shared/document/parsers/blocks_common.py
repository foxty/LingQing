"""Shared helpers for parser block IR production."""

from __future__ import annotations

import re
from typing import Any

_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")


def normalize_block_text(text: str) -> str:
    """Light cleanup for text stored in blocks."""
    cleaned = _BOLD_RE.sub(r"\1", text)
    return cleaned.strip()


def dedupe_consecutive_headings(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop consecutive heading blocks with identical text."""
    if not blocks:
        return blocks
    deduped: list[dict[str, Any]] = [blocks[0]]
    for block in blocks[1:]:
        if block.get("type") == "heading" and deduped[-1].get("type") == "heading":
            if (block.get("text") or "").strip() == (deduped[-1].get("text") or "").strip():
                continue
        deduped.append(block)
    return deduped
