"""URL/path helpers for persisted chart artifacts."""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlparse, urlunparse

from apps.config import get_charts_path

_SVG_SUFFIX = ".svg"
_PNG_SUFFIX = ".png"
CHART_STATIC_PATH = re.compile(
    r"^(?:/api)?/static/charts/(?P<filename>chart_[A-Za-z0-9_.-]+\.(?:png|svg))$",
    re.IGNORECASE,
)
CHART_PNG_FILENAME = re.compile(r"^chart_[A-Za-z0-9_.-]+\.png$", re.IGNORECASE)


def chart_png_url_for_svg_url(url: str) -> str:
    """Return the companion PNG URL for a chart static SVG URL (same stem)."""
    parsed = urlparse(url)
    path = parsed.path
    if not path.lower().endswith(_SVG_SUFFIX):
        return url
    png_path = f"{path[: -len(_SVG_SUFFIX)]}{_PNG_SUFFIX}"
    return urlunparse(parsed._replace(path=png_path))


def chart_static_png_filename(url_or_path: str) -> str | None:
    """Return a safe PNG basename for a chart static URL/path, or None."""
    cleaned = (url_or_path or "").strip()
    if not cleaned:
        return None
    path = urlparse(cleaned).path if cleaned.startswith(("http://", "https://")) else cleaned
    match = CHART_STATIC_PATH.match(path)
    if not match:
        return None
    name = match.group("filename")
    if name.lower().endswith(_SVG_SUFFIX):
        name = f"{name[: -len(_SVG_SUFFIX)]}{_PNG_SUFFIX}"
    if not CHART_PNG_FILENAME.fullmatch(name):
        return None
    return name


def read_chart_static_png_file(filename: str) -> bytes | None:
    """Read one companion PNG from the chart static directory."""
    if not CHART_PNG_FILENAME.fullmatch(filename):
        return None
    file_path = Path(get_charts_path()) / filename
    if not file_path.is_file():
        return None
    try:
        return file_path.read_bytes()
    except OSError:
        return None


def read_chart_static_png(url_or_path: str) -> bytes | None:
    """Resolve a chart static URL/path to PNG bytes on disk."""
    filename = chart_static_png_filename(url_or_path)
    if filename is None:
        return None
    return read_chart_static_png_file(filename)
