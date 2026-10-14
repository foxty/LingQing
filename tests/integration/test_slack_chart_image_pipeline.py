"""Integration: dual-write chart artifacts satisfy Slack upload fetch."""

import re
from unittest.mock import patch

import pytest

from apps.shared.chart.paths import chart_static_png_filename
from apps.shared.chart.renderer import render_chart
from apps.tenant_app_service.agent_ingress.slack.markdown_blocks import plan_slack_markdown
from apps.tenant_app_service.agent_ingress.slack.slack_image_fetcher import fetch_upload_block_bytes
from apps.tenant_app_service.agent_ingress.slack.slack_image_refs import SlackImageUploadSource

pytestmark = pytest.mark.integration

_MARKDOWN_IMAGE_URL = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")


@pytest.fixture
def charts_tmp_path(tmp_path):
    charts_dir = tmp_path / "charts"
    charts_dir.mkdir()
    return charts_dir


@pytest.mark.asyncio
async def test_rendered_chart_png_loadable_for_slack_upload_block(charts_tmp_path):
    data = '[{"month":"Jan","sales":100},{"month":"Feb","sales":120}]'
    api_base = "http://127.0.0.1:8000"

    with patch("apps.shared.chart.renderer.get_charts_path", return_value=str(charts_tmp_path)):
        with patch("apps.shared.chart.renderer.EnvConfig") as mock_config:
            mock_config.CHART_SERVICE_URL = api_base
            markdown = render_chart(
                chart_type="bar",
                data=data,
                title="Pipeline Sales",
                x_key="month",
                y_key="sales",
            )

    match = _MARKDOWN_IMAGE_URL.search(markdown)
    assert match is not None
    chart_svg_url = match.group(1)
    assert chart_svg_url.endswith(".svg")

    png_name = chart_static_png_filename(chart_svg_url)
    assert png_name is not None
    assert (charts_tmp_path / png_name).is_file()

    plan = plan_slack_markdown(markdown, api_origin=api_base)
    assert plan.image_count == 1
    block = plan.blocks[0]
    assert block["type"] == "_image_upload"
    assert block["source"] == SlackImageUploadSource.CHART
    assert block["filename"] == png_name

    with patch("apps.shared.chart.paths.get_charts_path", return_value=str(charts_tmp_path)):
        png_bytes = await fetch_upload_block_bytes(block)

    assert png_bytes is not None
    assert png_bytes.startswith(b"\x89PNG\r\n\x1a\n")
