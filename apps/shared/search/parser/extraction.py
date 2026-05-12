"""Extract plain text from stored raw_content payloads."""

from __future__ import annotations

from apps.shared.document.manifest import is_manifest_pointer


def extract_text_from_raw(raw_content: dict) -> str:
    """Extract plain text from raw_content for tokenization."""
    if not raw_content:
        return ""

    if is_manifest_pointer(raw_content):
        return ""

    text = raw_content.get("text")
    if text and isinstance(text, str):
        return text

    content = raw_content.get("content")
    if not content:
        return ""

    if isinstance(content, list):
        parts = []
        for segment in content:
            if isinstance(segment, dict):
                seg_text = segment.get("text", "")
                if seg_text:
                    parts.append(seg_text)
            elif isinstance(segment, str):
                parts.append(segment)
        return "\n".join(parts)

    if isinstance(content, str):
        return content

    return ""
