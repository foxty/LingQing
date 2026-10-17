"""On-disk layout for chart artifact bytes."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from apps.config import get_tenant_media_path

ChartImageFormat = Literal["svg", "png"]
CHART_IMAGE_FORMAT_SVG: ChartImageFormat = "svg"
CHART_IMAGE_FORMAT_PNG: ChartImageFormat = "png"


def chart_artifact_dir(tenant_id: int, chart_id: int) -> Path:
    return Path(get_tenant_media_path(tenant_id)) / "charts" / str(chart_id)


def write_chart_artifact_pair(tenant_id: int, chart_id: int, *, svg_bytes: bytes, png_bytes: bytes) -> None:
    base = chart_artifact_dir(tenant_id, chart_id)
    base.mkdir(parents=True, exist_ok=True)
    (base / "chart.svg").write_bytes(svg_bytes)
    (base / "chart.png").write_bytes(png_bytes)


def read_chart_artifact_file(tenant_id: int, chart_id: int, *, fmt: ChartImageFormat) -> bytes | None:
    name = "chart.svg" if fmt == CHART_IMAGE_FORMAT_SVG else "chart.png"
    file_path = chart_artifact_dir(tenant_id, chart_id) / name
    if not file_path.is_file():
        return None
    try:
        return file_path.read_bytes()
    except OSError:
        return None


def chart_image_media_type(fmt: ChartImageFormat) -> str:
    if fmt == CHART_IMAGE_FORMAT_SVG:
        return "image/svg+xml"
    return "image/png"
