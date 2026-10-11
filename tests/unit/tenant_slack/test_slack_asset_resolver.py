"""Tests for shared Slack image upload resolver."""

from unittest.mock import AsyncMock

import pytest

from apps.tenant_app_service.agent_ingress.slack.slack_asset_resolver import SlackAssetResolver

PNG = b"\x89PNG\r\n\x1a\nresolver"
HASH = "9" * 64


class _CountingClient:
    def __init__(self):
        self.upload_calls = 0

    async def upload_file(self, *, bot_token: str, filename: str, content: bytes) -> str:
        self.upload_calls += 1
        return f"F_{self.upload_calls}"

    async def file_permalink(self, *, bot_token: str, file_id: str) -> str | None:
        return f"https://slack.example/files/{file_id}"


def _document_upload_block() -> dict:
    return {
        "type": "_image_upload",
        "source": "document",
        "document_id": 2,
        "filename": f"{HASH}.png",
        "upload_filename": f"{HASH}.png",
        "alt_text": "Deck",
        "url": f"https://api.example.com/documents/2/images/{HASH}.png",
        "fallback_mrkdwn": "fallback",
    }


@pytest.mark.asyncio
async def test_resolver_dedupes_identical_upload_blocks():
    client = _CountingClient()
    fetch_calls = 0

    async def fetch(_block: dict) -> bytes:
        nonlocal fetch_calls
        fetch_calls += 1
        return PNG

    resolver = SlackAssetResolver(client=client, bot_token="xoxb", image_fetcher=fetch)
    block = _document_upload_block()

    resolved = await resolver.resolve_blocks([block, block])

    assert client.upload_calls == 1
    assert fetch_calls == 1
    assert resolved[0]["slack_file"]["id"] == resolved[1]["slack_file"]["id"]


@pytest.mark.asyncio
async def test_prepare_canvas_markdown_rewrites_html_img_src():
    client = _CountingClient()
    src = f"/documents/3/images/{HASH}.png"

    async def fetch(_block: dict) -> bytes:
        return PNG

    resolver = SlackAssetResolver(client=client, bot_token="xoxb", image_fetcher=fetch)
    markdown = f'<figure><img src="{src}" alt="Deck page 4"></figure>'

    updated = await resolver.prepare_canvas_markdown(
        markdown,
        portal_origin="https://portal.example.com",
        api_origin="https://api.example.com",
    )

    assert src not in updated
    assert "https://slack.example/files/F_1" in updated


@pytest.mark.asyncio
async def test_prepare_canvas_markdown_keeps_src_when_permalink_missing():
    client = _CountingClient()
    client.file_permalink = AsyncMock(return_value=None)  # type: ignore[method-assign]
    src = f"/documents/3/images/{HASH}.png"

    async def fetch(_block: dict) -> bytes:
        return PNG

    resolver = SlackAssetResolver(client=client, bot_token="xoxb", image_fetcher=fetch)
    markdown = f"![Deck]({src})"

    updated = await resolver.prepare_canvas_markdown(
        markdown,
        portal_origin=None,
        api_origin="https://api.example.com",
    )

    assert updated == markdown
