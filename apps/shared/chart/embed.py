"""Chart markdown references and public image URLs."""

from __future__ import annotations

import re
from urllib.parse import urlparse

from apps.config import EnvConfig
from apps.shared.utils.markdown_images import iter_markdown_image_tuples

CHART_RESOURCE_IMAGE_PATH = re.compile(
    r"^(?:/api)?/charts/(?P<chart_id>\d+)/image\.(?:svg|png)$",
    re.IGNORECASE,
)

EMBEDDED_CHART_IDS_METADATA_KEY = "embedded_chart_ids"


def path_from_url(url_or_path: str) -> str:
    cleaned = (url_or_path or "").strip()
    if cleaned.startswith(("http://", "https://")):
        return urlparse(cleaned).path
    return cleaned.split("?")[0].split("#")[0]


def chart_image_url(chart_id: int, *, fmt: str = "svg") -> str:
    api_base = EnvConfig.CHART_SERVICE_URL.rstrip("/")
    ext = fmt.lower()
    return f"{api_base}/charts/{chart_id}/image.{ext}"


def chart_markdown_image(title: str, chart_id: int) -> str:
    safe_title = (title or "Chart").replace("\n", " ")
    return f"\n\n![{safe_title}]({chart_image_url(chart_id, fmt='svg')})\n\n"


def chart_id_from_image_url(url_or_path: str) -> int | None:
    match = CHART_RESOURCE_IMAGE_PATH.match(path_from_url(url_or_path))
    if not match:
        return None
    return int(match.group("chart_id"))


def embedded_chart_ids_from_markdown(markdown: str) -> list[int]:
    ids: list[int] = []
    seen: set[int] = set()
    for _alt, src in iter_markdown_image_tuples(markdown):
        chart_id = chart_id_from_image_url(src)
        if chart_id is not None and chart_id not in seen:
            seen.add(chart_id)
            ids.append(chart_id)
    return ids


def merge_embedded_chart_ids_metadata(content: str, metadata: dict | None) -> dict:
    merged = dict(metadata or {})
    merged[EMBEDDED_CHART_IDS_METADATA_KEY] = embedded_chart_ids_from_markdown(content)
    return merged
