"""Classify and locate image references in agent Markdown for Slack delivery."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

DOCUMENT_IMAGE_PATH = re.compile(
    r"^(?:/api)?/documents/(?P<document_id>\d+)/images/(?P<filename>[a-f0-9]{64}\.(?:png|jpe?g|gif))$",
    re.IGNORECASE,
)
MARKDOWN_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
HTML_IMG_SRC_RE = re.compile(r"""<img\b[^>]*\bsrc=["']([^"']+)["']""", re.IGNORECASE)


@dataclass(frozen=True)
class DocumentImageRef:
    document_id: int
    filename: str


def parse_document_image_location(url_or_path: str) -> DocumentImageRef | None:
    """Return document id and filename when ``url_or_path`` is a parse image path."""
    cleaned = (url_or_path or "").strip()
    if not cleaned:
        return None
    path = urlparse(cleaned).path if cleaned.startswith(("http://", "https://")) else cleaned
    match = DOCUMENT_IMAGE_PATH.match(path)
    if not match:
        return None
    return DocumentImageRef(int(match.group("document_id")), match.group("filename"))


def upload_block_cache_key(block: dict[str, Any]) -> str:
    if block.get("source") == "document":
        return f"document:{block.get('document_id')}:{block.get('filename')}"
    if block.get("source") == "chart":
        return f"chart:{block.get('filename')}"
    return f"url:{block.get('url')}"


def iter_markdown_image_refs(markdown: str) -> list[tuple[str, str]]:
    """Return ``(alt, src)`` pairs from markdown and embedded HTML ``img`` tags."""
    refs: list[tuple[str, str]] = []
    seen: set[str] = set()
    for alt, src in MARKDOWN_IMAGE_RE.findall(markdown):
        if src not in seen:
            seen.add(src)
            refs.append((alt, src))
    for src in HTML_IMG_SRC_RE.findall(markdown):
        if src not in seen:
            seen.add(src)
            refs.append(("", src))
    return refs
