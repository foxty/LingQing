"""Chart markdown URL helpers."""

from apps.shared.chart.embed import chart_image_url, chart_markdown_image


def test_chart_image_url_relative_when_service_url_unset(monkeypatch):
    monkeypatch.setattr("apps.shared.chart.embed.EnvConfig.CHART_SERVICE_URL", None)
    assert chart_image_url(42, fmt="svg") == "/charts/42/image.svg"


def test_chart_markdown_image_includes_url():
    md = chart_markdown_image("Sales", 7)
    assert "![Sales]" in md
    assert "/charts/7/image.svg" in md
