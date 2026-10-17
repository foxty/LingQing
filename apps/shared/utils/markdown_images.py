"""Shared helpers for markdown image syntax."""

from __future__ import annotations

import re

MARKDOWN_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")


def iter_markdown_image_tuples(markdown: str) -> list[tuple[str, str]]:
    """Return ``(alt, src)`` for each ``![alt](src)`` in order (no deduplication)."""
    return MARKDOWN_IMAGE_RE.findall(markdown or "")
