"""URL adapter for OpenAPI schema sources.

This module intentionally keeps source URL adaptation logic separate from
schema parsing/loading to avoid coupling parser code to provider-specific URL
formats.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse


@dataclass(frozen=True)
class SourceUrlAdaptResult:
    """Result of source URL adaptation."""

    url: str
    adapted: bool
    reason: str | None = None


class OpenApiSourceUrlAdapter:
    """Adapter for normalizing known OpenAPI source URL formats."""

    @staticmethod
    def adapt(url: str) -> SourceUrlAdaptResult:
        parsed = urlparse(url)

        # GitHub blob URL -> raw URL
        # e.g. https://github.com/org/repo/blob/main/openapi.yaml
        if parsed.netloc in {"github.com", "www.github.com"}:
            segments = [segment for segment in parsed.path.split("/") if segment]
            if len(segments) >= 5 and segments[2] == "blob":
                owner = segments[0]
                repo = segments[1]
                ref = segments[3]
                file_path = "/".join(segments[4:])
                raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/{ref}/{file_path}"
                return SourceUrlAdaptResult(
                    url=raw_url,
                    adapted=True,
                    reason="github-blob-to-raw",
                )

        return SourceUrlAdaptResult(url=url, adapted=False)
