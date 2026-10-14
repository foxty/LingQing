"""Unit tests for Slack Markdown delivery side effects."""

from typing import Any
from unittest.mock import AsyncMock

import pytest
from slack_sdk.errors import SlackApiError

from apps.tenant_app_service.agent_ingress.slack.markdown_blocks import MarkdownRenderError, SlackMarkdownPolicy
from apps.tenant_app_service.agent_ingress.slack.markdown_delivery import deliver_markdown_to_slack
from apps.tenant_app_service.agent_ingress.slack.slack_image_fetcher import make_slack_image_fetcher

PNG = b"\x89PNG\r\n\x1a\nfake"


class _SlackStub:
    def __init__(self, *, fail_canvas: bool = False, invalid_blocks: bool = False):
        self.posts: list[dict[str, Any]] = []
        self.updates: list[dict[str, Any]] = []
        self.uploads: list[str] = []
        self.canvases: list[str] = []
        self.grants: list[dict[str, Any]] = []
        self.fail_canvas = fail_canvas
        self.invalid_blocks = invalid_blocks
        self._rejected = False

    async def chat_post_message(self, **kwargs: Any) -> dict[str, Any]:
        self._maybe_reject()
        self.posts.append(kwargs)
        return {"ok": True, "ts": f"{len(self.posts)}.0"}

    async def chat_update(self, **kwargs: Any) -> dict[str, Any]:
        self._maybe_reject()
        self.updates.append(kwargs)
        return {"ok": True}

    async def upload_file(self, *, bot_token: str, filename: str, content: bytes) -> str:
        self.uploads.append(filename)
        return "F_UPLOAD"

    async def file_permalink(self, *, bot_token: str, file_id: str) -> str | None:
        return f"https://slack.example/files/{file_id}"

    async def create_canvas(self, *, bot_token: str, title: str, markdown: str) -> str:
        if self.fail_canvas:
            raise RuntimeError("canvas down")
        self.canvases.append(markdown)
        return "FCANVAS"

    async def grant_canvas_read(
        self, *, bot_token: str, canvas_id: str, channel_id: str | None = None, user_id: str | None = None
    ) -> None:
        self.grants.append({"canvas_id": canvas_id, "channel_id": channel_id, "user_id": user_id})

    async def canvas_permalink(self, *, bot_token: str, canvas_id: str) -> str:
        return f"https://slack.example/docs/{canvas_id}"

    def _maybe_reject(self) -> None:
        if self.invalid_blocks and not self._rejected:
            self._rejected = True
            raise SlackApiError("invalid", {"error": "invalid_blocks"})


async def _no_fetch(_block: dict) -> bytes | None:
    raise AssertionError("image fetch was not expected")


async def _png_fetch(_block: dict) -> bytes | None:
    return PNG


def _types(messages: list[dict[str, Any]]) -> list[str]:
    types: list[str] = []
    for message in messages:
        types.extend(block["type"] for block in message["blocks"])
    return types


@pytest.mark.asyncio
async def test_inline_table_and_public_image_append_actions():
    slack = _SlackStub()
    text = "Hello\n\n| A | B |\n| --- | --- |\n| 1 | 2 |\n\n![Plot](https://cdn.example.com/plot.png)"

    await deliver_markdown_to_slack(
        client=slack,
        bot_token="xoxb-test",
        channel_id="C1",
        markdown=text,
        message_id="msg_1",
        thread_ts="1.2",
        image_fetcher=_no_fetch,
    )

    assert slack.uploads == []
    assert slack.canvases == []
    assert _types(slack.posts) == ["section", "table", "image", "actions"]
    assert slack.posts[0]["blocks"][-1]["block_id"] == "feedback_msg_1"


@pytest.mark.asyncio
async def test_owned_chart_svg_uploads_png_from_disk(monkeypatch, tmp_path):
    slack = _SlackStub()
    png_name = "chart_1_daily_ab12cd34.png"
    (tmp_path / png_name).write_bytes(PNG)
    monkeypatch.setattr(
        "apps.shared.chart.paths.get_charts_path",
        lambda: str(tmp_path),
    )
    fetch = make_slack_image_fetcher(db=AsyncMock(), tenant_id=1, user_id=1, user_role="member")
    chart_svg = f"http://127.0.0.1:8000/static/charts/{png_name.replace('.png', '.svg')}"

    await deliver_markdown_to_slack(
        client=slack,
        bot_token="xoxb-test",
        channel_id="C1",
        markdown=f"![Daily]({chart_svg})",
        message_id=None,
        thread_ts=None,
        api_origin="http://127.0.0.1:8000",
        image_fetcher=fetch,
    )

    assert slack.uploads == [png_name]
    assert len(slack.posts) == 1
    assert slack.posts[0]["blocks"][0]["type"] == "image"
    assert slack.posts[0]["blocks"][0]["slack_file"] == {"id": "F_UPLOAD"}


@pytest.mark.asyncio
async def test_chart_image_delivery_skips_http_fetch(monkeypatch, tmp_path):
    slack = _SlackStub()
    png_name = "chart_9_slack_ab12cd34.png"
    (tmp_path / png_name).write_bytes(PNG)
    monkeypatch.setattr(
        "apps.shared.chart.paths.get_charts_path",
        lambda: str(tmp_path),
    )

    async def _must_not_fetch_url(_url: str) -> bytes | None:
        raise AssertionError("owned URL fetch must not run for chart upload blocks")

    monkeypatch.setattr(
        "apps.tenant_app_service.agent_ingress.slack.slack_image_fetcher.fetch_owned_url_bytes",
        _must_not_fetch_url,
    )
    fetch = make_slack_image_fetcher(db=AsyncMock(), tenant_id=1, user_id=1, user_role="member")
    chart_svg = f"http://127.0.0.1:8000/static/charts/{png_name.replace('.png', '.svg')}"

    await deliver_markdown_to_slack(
        client=slack,
        bot_token="xoxb-test",
        channel_id="C1",
        markdown=f"![Daily]({chart_svg})",
        message_id=None,
        thread_ts=None,
        api_origin="http://127.0.0.1:8000",
        image_fetcher=fetch,
    )

    assert slack.uploads == [png_name]


@pytest.mark.asyncio
async def test_private_image_uploads_and_references_file():
    slack = _SlackStub()
    text = "![Plot](http://127.0.0.1:8000/static/plot.png)"

    await deliver_markdown_to_slack(
        client=slack,
        bot_token="xoxb-test",
        channel_id="C1",
        markdown=text,
        message_id=None,
        thread_ts=None,
        api_origin="http://127.0.0.1:8000",
        image_fetcher=_png_fetch,
    )

    assert slack.uploads == ["plot.png"]
    image = slack.posts[0]["blocks"][0]
    assert image["type"] == "image"
    assert image["slack_file"] == {"id": "F_UPLOAD"}


@pytest.mark.asyncio
async def test_upload_failure_falls_back_to_chart_link():
    slack = _SlackStub()

    async def _empty(_url: str) -> bytes | None:
        return None

    await deliver_markdown_to_slack(
        client=slack,
        bot_token="xoxb-test",
        channel_id="C1",
        markdown="![Plot](http://127.0.0.1:8000/static/plot.png)",
        message_id=None,
        thread_ts=None,
        api_origin="http://127.0.0.1:8000",
        image_fetcher=_empty,
    )

    assert slack.uploads == []
    assert slack.posts[0]["blocks"][0]["type"] == "section"
    assert "plot.png" in slack.posts[0]["blocks"][0]["text"]["text"]


@pytest.mark.asyncio
async def test_oversized_table_posts_canvas_link_without_table_block():
    slack = _SlackStub()
    lines = ["| A | B |", "| --- | --- |"]
    lines.extend(f"| r{index} | c |" for index in range(11))

    await deliver_markdown_to_slack(
        client=slack,
        bot_token="xoxb-test",
        channel_id="C1",
        markdown="\n".join(lines),
        message_id="msg_1",
        thread_ts=None,
        image_fetcher=_no_fetch,
    )

    assert slack.canvases
    assert "| r10 | c |" in slack.canvases[0]
    assert slack.grants[0]["channel_id"] == "C1"
    posted = " ".join(block["text"]["text"] for block in slack.posts[0]["blocks"] if block["type"] == "section")
    assert "https://slack.example/docs/FCANVAS" in posted
    assert "actions" == slack.posts[0]["blocks"][-1]["type"]
    assert all(block["type"] != "table" for block in slack.posts[0]["blocks"])


@pytest.mark.asyncio
async def test_direct_message_canvas_is_shared_with_user():
    slack = _SlackStub()
    lines = ["| A | B |", "| --- | --- |", *(f"| r{index} | c |" for index in range(11))]

    await deliver_markdown_to_slack(
        client=slack,
        bot_token="xoxb-test",
        channel_id="D1",
        markdown="\n".join(lines),
        message_id=None,
        thread_ts=None,
        slack_user_id="U1",
        channel_type="im",
        image_fetcher=_no_fetch,
    )

    assert slack.grants[0]["user_id"] == "U1"
    assert slack.grants[0]["channel_id"] is None


@pytest.mark.asyncio
async def test_canvas_failure_falls_back_to_mrkdwn():
    slack = _SlackStub(fail_canvas=True)
    lines = ["| Name | Role |", "| --- | --- |", *(f"| u{index} | m |" for index in range(11))]

    await deliver_markdown_to_slack(
        client=slack,
        bot_token="xoxb-test",
        channel_id="C1",
        markdown="\n".join(lines),
        message_id=None,
        thread_ts=None,
        image_fetcher=_no_fetch,
    )

    assert slack.canvases == []
    text = slack.posts[0]["blocks"][0]["text"]["text"]
    assert "Open in Canvas" not in text
    assert "Name" in text


@pytest.mark.asyncio
async def test_truncated_cell_adds_canvas_context():
    slack = _SlackStub()
    policy = SlackMarkdownPolicy(cell_max_chars=5)

    await deliver_markdown_to_slack(
        client=slack,
        bot_token="xoxb-test",
        channel_id="C1",
        markdown="| A |\n| --- |\n| hello world |",
        message_id=None,
        thread_ts=None,
        policy=policy,
        image_fetcher=_no_fetch,
    )

    blocks = slack.posts[0]["blocks"]
    assert blocks[0]["type"] == "table"
    assert blocks[0]["rows"][1][0]["text"] == "hell…"
    assert blocks[1]["type"] == "context"
    assert "See Canvas" in blocks[1]["elements"][0]["text"]


@pytest.mark.asyncio
async def test_invalid_blocks_retries_as_mrkdwn():
    slack = _SlackStub(invalid_blocks=True)
    text = "| Name | Role |\n| --- | --- |\n| Ada | Admin |"

    await deliver_markdown_to_slack(
        client=slack,
        bot_token="xoxb-test",
        channel_id="C1",
        markdown=text,
        message_id=None,
        thread_ts=None,
        update_ts="9.9",
        image_fetcher=_no_fetch,
    )

    assert slack.posts == []
    assert len(slack.updates) == 1
    assert all(block["type"] != "table" for block in slack.updates[0]["blocks"])
    assert "Ada" in slack.updates[0]["text"]


@pytest.mark.asyncio
async def test_prose_over_block_limit_splits_and_actions_stay_on_last():
    slack = _SlackStub()
    policy = SlackMarkdownPolicy(max_blocks=2)

    await deliver_markdown_to_slack(
        client=slack,
        bot_token="xoxb-test",
        channel_id="C1",
        markdown="one\n\n---\n\ntwo\n\n---\n\nthree",
        message_id="msg_1",
        thread_ts="4.0",
        update_ts="3.0",
        policy=policy,
        image_fetcher=_no_fetch,
    )

    assert len(slack.updates) == 1
    assert len(slack.posts) == 2
    assert all(block["type"] != "actions" for block in slack.updates[0]["blocks"])
    assert slack.posts[0]["blocks"][-1]["type"] != "actions"
    assert slack.posts[1]["blocks"][-1]["type"] == "actions"


@pytest.mark.asyncio
async def test_document_image_without_requester_context_falls_back_to_link():
    slack = _SlackStub()
    image_name = "a" * 64
    text = f"![Deck](/documents/2/images/{image_name}.png)"

    await deliver_markdown_to_slack(
        client=slack,
        bot_token="xoxb-test",
        channel_id="C1",
        markdown=text,
        message_id=None,
        thread_ts=None,
        api_origin="https://api.example.com",
    )

    assert slack.uploads == []
    block = slack.posts[0]["blocks"][0]
    assert block["type"] == "section"
    assert image_name in block["text"]["text"]


@pytest.mark.asyncio
async def test_document_image_uploads_to_slack_file_block():
    slack = _SlackStub()
    image_name = "b" * 64
    text = f"![Deck](/documents/2/images/{image_name}.png)"

    await deliver_markdown_to_slack(
        client=slack,
        bot_token="xoxb-test",
        channel_id="C1",
        markdown=text,
        message_id=None,
        thread_ts=None,
        api_origin="https://api.example.com",
        image_fetcher=_png_fetch,
    )

    assert slack.uploads == [f"{image_name}.png"]
    image = slack.posts[0]["blocks"][0]
    assert image["type"] == "image"
    assert image["slack_file"] == {"id": "F_UPLOAD"}


@pytest.mark.asyncio
async def test_canvas_rewrites_document_image_permalink():
    slack = _SlackStub()
    image_name = "c" * 64
    src = f"/documents/2/images/{image_name}.png"
    lines = ["| A | B |", "| --- | --- |", *(f"| r{index} | c |" for index in range(11))]
    text = f"![Deck]({src})\n\n" + "\n".join(lines)

    await deliver_markdown_to_slack(
        client=slack,
        bot_token="xoxb-test",
        channel_id="C1",
        markdown=text,
        message_id=None,
        thread_ts=None,
        api_origin="https://api.example.com",
        image_fetcher=_png_fetch,
    )

    assert slack.uploads == [f"{image_name}.png"]
    assert "https://slack.example/files/F_UPLOAD" in slack.canvases[0]
    assert src not in slack.canvases[0]


@pytest.mark.asyncio
async def test_unrecognized_markdown_still_posts(monkeypatch):
    slack = _SlackStub()

    def _boom(self):
        raise MarkdownRenderError("mystery")

    monkeypatch.setattr(
        "apps.tenant_app_service.agent_ingress.slack.markdown_blocks._MarkdownWalker.walk",
        _boom,
    )

    await deliver_markdown_to_slack(
        client=slack,
        bot_token="xoxb-test",
        channel_id="C1",
        markdown="Hello **there**",
        message_id="msg_1",
        thread_ts=None,
        image_fetcher=_no_fetch,
    )

    assert "Hello *there*" in slack.posts[0]["blocks"][0]["text"]["text"]
    assert slack.posts[0]["blocks"][-1]["type"] == "actions"
