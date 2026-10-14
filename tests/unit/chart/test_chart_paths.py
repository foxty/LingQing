"""Tests for chart URL/path helpers."""

from pathlib import Path
from unittest.mock import patch

from apps.shared.chart.paths import (
    chart_png_url_for_svg_url,
    chart_static_png_filename,
    read_chart_static_png,
    read_chart_static_png_file,
)

PNG = b"\x89PNG\r\n\x1a\nchart-bytes"


def test_chart_png_url_for_svg_url():
    assert (
        chart_png_url_for_svg_url("http://localhost:8000/static/charts/chart_1_foo_ab.svg")
        == "http://localhost:8000/static/charts/chart_1_foo_ab.png"
    )
    assert chart_png_url_for_svg_url("http://localhost:8000/static/charts/chart.png") == (
        "http://localhost:8000/static/charts/chart.png"
    )


def test_chart_static_png_filename_from_svg_or_png():
    base = "/static/charts/chart_1_foo_ab12cd34.svg"
    assert chart_static_png_filename(base) == "chart_1_foo_ab12cd34.png"
    assert chart_static_png_filename(base.replace(".svg", ".png")) == "chart_1_foo_ab12cd34.png"
    assert chart_static_png_filename("/static/charts/evil/../../../etc/passwd") is None


def test_read_chart_static_png_file(tmp_path):
    name = "chart_1_test_ab12cd34.png"
    (tmp_path / name).write_bytes(PNG)
    with patch("apps.shared.chart.paths.get_charts_path", return_value=str(tmp_path)):
        assert read_chart_static_png_file(name) == PNG
        assert read_chart_static_png(f"/static/charts/{name.replace('.png', '.svg')}") == PNG
