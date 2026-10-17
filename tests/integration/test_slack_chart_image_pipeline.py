"""Integration: chart artifact URLs satisfy Slack upload fetch."""

import re
from unittest.mock import AsyncMock, patch

import pytest
from apps.shared.chart.renderer import render_chart
from apps.tenant_app_service.agent_ingress.slack.markdown_blocks import plan_slack_markdown
from apps.tenant_app_service.agent_ingress.slack.slack_image_fetcher import fetch_upload_block_bytes
from apps.tenant_app_service.agent_ingress.slack.slack_image_refs import SlackImageUploadSource

pytestmark = pytest.mark.integration

_MARKDOWN_IMAGE_URL = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")


@pytest.mark.asyncio
async def test_registered_chart_png_loadable_for_slack_upload_block():
    data = '[{"month":"Jan","sales":100},{"month":"Feb","sales":120}]'
    api_base = "http://127.0.0.1:8000"

    rendered = render_chart(
        chart_type="bar",
        data=data,
        title="Pipeline Sales",
        x_key="month",
        y_key="sales",
    )
    assert rendered.png_bytes.startswith(b"\x89PNG\r\n\x1a\n")

    markdown = f"\n\n![Pipeline Sales]({api_base}/charts/1/image.svg)\n\n"

    match = _MARKDOWN_IMAGE_URL.search(markdown)
    assert match is not None
    assert "/charts/1/" in match.group(1)

    plan = plan_slack_markdown(markdown, api_origin=api_base)
    assert plan.image_count == 1
    block = plan.blocks[0]
    assert block["type"] == "_image_upload"
    assert block["source"] == SlackImageUploadSource.CHART_RESOURCE
    assert block["chart_id"] == 1

    db = AsyncMock()
    with patch(
        "apps.tenant_app_service.agent_ingress.slack.slack_image_fetcher.ChartService.read_image",
        new=AsyncMock(return_value=(rendered.png_bytes, "image/png")),
    ):
        png_bytes = await fetch_upload_block_bytes(
            block,
            db=db,
            tenant_id=1,
            user_id=1,
            user_role="member",
        )

    assert png_bytes == rendered.png_bytes


@pytest.mark.asyncio
async def test_chart_resource_fetch_honors_acl_denial():
    from apps.shared.core.exceptions import AuthorizationError

    api_base = "http://127.0.0.1:8000"
    markdown = f"\n\n![Denied]({api_base}/charts/99/image.svg)\n\n"
    plan = plan_slack_markdown(markdown, api_origin=api_base)
    block = plan.blocks[0]

    async def _deny(*_args, **_kwargs):
        raise AuthorizationError("Access denied")

    with patch(
        "apps.tenant_app_service.agent_ingress.slack.slack_image_fetcher.ChartService.read_image",
        new=AsyncMock(side_effect=_deny),
    ):
        png_bytes = await fetch_upload_block_bytes(
            block,
            db=AsyncMock(),
            tenant_id=1,
            user_id=2,
            user_role="member",
        )

    assert png_bytes is None
