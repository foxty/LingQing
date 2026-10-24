"""Optional layout overlays for report charts (subtitle, reference lines, annotations)."""

from __future__ import annotations

import json
from typing import Any

import plotly.graph_objects as go

from apps.shared.chart.data_processor import coerce_numeric_value, infer_percent_tickformat


def parse_json_list(raw: str | None, *, field_name: str) -> list[dict[str, Any]]:
    if raw is None or not str(raw).strip():
        return []
    parsed = json.loads(raw)
    if not isinstance(parsed, list):
        raise ValueError(f"{field_name} must be a JSON array")
    return [item for item in parsed if isinstance(item, dict)]


def apply_chart_enhancements(
    fig: go.Figure,
    *,
    subtitle: str | None,
    reference_lines: list[dict[str, Any]] | None,
    annotations: list[dict[str, Any]] | None,
    y_axis_percent: bool,
    y_numeric_samples: list[float] | None,
) -> None:
    """Mutate figure layout with subtitle, h-lines, and point annotations."""
    if subtitle and subtitle.strip():
        existing = fig.layout.title
        title_text = (existing.text if existing and existing.text else "") or ""
        if "<br><sub>" not in title_text:
            fig.update_layout(title_text=f"{title_text}<br><sub>{subtitle.strip()}</sub>")

    if y_axis_percent:
        tick = infer_percent_tickformat(y_numeric_samples or [])
        fig.update_layout(yaxis=dict(tickformat=tick))

    for line in reference_lines or []:
        y = coerce_numeric_value(line.get("y"))
        if y is None:
            continue
        label = line.get("label") or line.get("text")
        color = line.get("color") or "rgba(102, 126, 234, 0.75)"
        fig.add_hline(
            y=float(y),
            line_dash=line.get("dash") or "dash",
            line_color=color,
            line_width=float(line.get("width") or 1.5),
            annotation_text=str(label) if label else None,
            annotation_position=line.get("annotation_position") or "right",
        )

    for ann in annotations or []:
        text = ann.get("text")
        if not text:
            continue
        kwargs: dict[str, Any] = {
            "text": str(text),
            "showarrow": bool(ann.get("showarrow", True)),
            "font": dict(size=int(ann.get("font_size") or 12), color=ann.get("color") or "#2c3e50"),
        }
        if "x" in ann:
            kwargs["x"] = ann["x"]
        if "y" in ann:
            y_val = coerce_numeric_value(ann["y"])
            kwargs["y"] = float(y_val) if y_val is not None else ann["y"]
        if ann.get("xref"):
            kwargs["xref"] = ann["xref"]
        if ann.get("yref"):
            kwargs["yref"] = ann["yref"]
        fig.add_annotation(**kwargs)
