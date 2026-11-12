"""Slack turn-duration footer: rounding, placement, and what must stay unchanged."""

from __future__ import annotations

import math
import re
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from slack_sdk.errors import SlackApiError

from apps.tenant_app_service.agent_ingress.slack.domain import SlackMessageEvent
from apps.tenant_app_service.agent_ingress.slack.ingress_service import SlackIngressService
from apps.tenant_app_service.agent_ingress.slack.markdown_delivery import (
    SlackOutboundMessage,
    _reserve_trailing_blocks,
    deliver_markdown_to_slack,
)
from apps.tenant_app_service.agent_ingress.slack.messages import (
    SLACK_EMPTY_REPLY_FALLBACK,
    SlackMessageKey,
    slack_user_message,
)
from apps.tenant_app_service.agent_ingress.slack.turn_duration import (
    TURN_DURATION_BLOCK_ID,
    apply_turn_footer_to_outbound,
    format_slack_turn_footer,
)

_FOOTER_RE = re.compile(r"^Took (?:<0\.1s|\d+\.\ds|\d+m \d+\.\ds)$")
_START = datetime(2026, 1, 1, tzinfo=UTC)


def _window(seconds: float) -> tuple[datetime, datetime]:
    return _START, _START + timedelta(seconds=seconds)


class _SlackStub:
    def __init__(self, *, reject_times: int = 0):
        self.posts: list[dict[str, Any]] = []
        self.updates: list[dict[str, Any]] = []
        self.reject_times = reject_times
        self._calls = 0

    async def chat_post_message(self, **kwargs: Any) -> dict[str, Any]:
        self._calls += 1
        if self._calls <= self.reject_times:
            raise SlackApiError("invalid", {"error": "invalid_blocks"})
        self.posts.append(kwargs)
        return {"ok": True, "ts": f"{len(self.posts)}.0"}

    async def chat_update(self, **kwargs: Any) -> dict[str, Any]:
        self._calls += 1
        if self._calls <= self.reject_times:
            raise SlackApiError("invalid", {"error": "invalid_blocks"})
        self.updates.append(kwargs)
        return {"ok": True}


async def _no_fetch(_block: dict) -> bytes | None:
    raise AssertionError("image fetch was not expected")


def _footer_texts(blocks: list[dict[str, Any]]) -> list[str]:
    found: list[str] = []
    for block in blocks:
        if block.get("block_id") == TURN_DURATION_BLOCK_ID:
            found.append(block["elements"][0]["text"])
    return found


def _section_text(blocks: list[dict[str, Any]]) -> str:
    return "\n".join(
        str((block.get("text") or {}).get("text") or "") for block in blocks if block.get("type") == "section"
    )


@pytest.mark.parametrize(
    ("elapsed", "expected"),
    [
        (0.04, "Took <0.1s"),
        (0.05, "Took 0.1s"),
        (0.44, "Took 0.4s"),
        (0.45, "Took 0.5s"),
        (12.34, "Took 12.3s"),
        (12.35, "Took 12.4s"),
        (59.94, "Took 59.9s"),
        (59.96, "Took 1m 0.0s"),
        (60, "Took 1m 0.0s"),
        (90.16, "Took 1m 30.2s"),
        (119.96, "Took 2m 0.0s"),
    ],
)
def test_format_slack_turn_footer_rounds_half_up(elapsed: float, expected: str) -> None:
    assert format_slack_turn_footer(elapsed) == expected
    assert _FOOTER_RE.match(expected)


@pytest.mark.parametrize("elapsed", [None, -0.01, -1, math.nan, math.inf, True])
def test_format_slack_turn_footer_hides_invalid_duration(elapsed: float | None) -> None:
    assert format_slack_turn_footer(elapsed) is None


def test_apply_turn_footer_to_outbound_uses_preformatted_footer() -> None:
    body = [{"type": "section", "text": {"type": "mrkdwn", "text": "Stopped."}}]
    text, blocks = apply_turn_footer_to_outbound(
        text="Stopped.",
        blocks=body,
        footer_text="Took 1.2s",
    )
    assert text == "Stopped.\nTook 1.2s"
    assert blocks[-1]["block_id"] == TURN_DURATION_BLOCK_ID


def test_apply_turn_footer_to_outbound_computes_from_turn_start() -> None:
    started, now = _window(5.0)
    body = [{"type": "section", "text": {"type": "mrkdwn", "text": "Done."}}]
    text, blocks = apply_turn_footer_to_outbound(
        text="Done.",
        blocks=body,
        turn_started_at=started,
        now=now,
    )
    assert text.endswith("Took 5.0s")
    assert blocks[-1]["block_id"] == TURN_DURATION_BLOCK_ID


def test_each_turn_uses_its_own_elapsed_time() -> None:
    longer = format_slack_turn_footer(90.16)
    shorter = format_slack_turn_footer(12.34)
    assert longer == "Took 1m 30.2s"
    assert shorter == "Took 12.3s"
    assert format_slack_turn_footer(90.16 + 12.34) != shorter


def test_footer_copy_has_no_identity_or_conversation_text() -> None:
    footer = format_slack_turn_footer(12.35)
    assert footer is not None
    assert _FOOTER_RE.match(footer)
    assert "U123" not in footer
    assert "prompt" not in footer.lower()


def test_reserve_trailing_blocks_leaves_room_for_footer_and_feedback() -> None:
    blocks = [{"type": "section", "text": {"type": "mrkdwn", "text": str(index)}} for index in range(49)]
    fitted = _reserve_trailing_blocks([SlackOutboundMessage(text="body", blocks=blocks)], trailing=2)
    assert len(fitted) == 2
    assert len(fitted[0].blocks) == 48
    assert len(fitted[1].blocks) == 1
    assert fitted[1].blocks[0]["text"]["text"] == "48"
    assert all(block["text"]["text"] != "48" for block in fitted[0].blocks)


@pytest.mark.asyncio
async def test_final_reply_footer_is_separate_from_body():
    slack = _SlackStub()
    started, now = _window(12.34)
    body = "The weather is clear."

    await deliver_markdown_to_slack(
        client=slack,
        bot_token="xoxb-test",
        channel_id="D1",
        markdown=body,
        message_id="msg_1",
        thread_ts="1.0",
        update_ts="1.1",
        image_fetcher=_no_fetch,
        turn_started_at=started,
        now=now,
    )

    blocks = slack.updates[0]["blocks"]
    assert _section_text(blocks) == body
    assert _footer_texts(blocks) == ["Took 12.3s"]
    assert blocks[-2]["type"] == "actions"
    assert blocks[-1]["block_id"] == TURN_DURATION_BLOCK_ID
    assert slack.updates[0]["text"] == f"{body}\nTook 12.3s"
    assert "Took 12.3s" not in _section_text(blocks)


@pytest.mark.asyncio
async def test_direct_and_channel_replies_use_the_same_footer():
    started, now = _window(12.35)
    footers: list[str] = []
    for channel_type, channel_id in (("im", "D42"), ("channel", "C99")):
        slack = _SlackStub()
        await deliver_markdown_to_slack(
            client=slack,
            bot_token="xoxb-test",
            channel_id=channel_id,
            markdown="Same answer",
            message_id="msg_1",
            thread_ts="1.0",
            channel_type=channel_type,
            slack_user_id="U_SECRET",
            image_fetcher=_no_fetch,
            turn_started_at=started,
            now=now,
        )
        footer = _footer_texts(slack.posts[0]["blocks"])[0]
        footers.append(footer)
        assert channel_id not in footer
        assert "U_SECRET" not in footer
        assert _section_text(slack.posts[0]["blocks"]) == "Same answer"
    assert footers == ["Took 12.4s", "Took 12.4s"]


@pytest.mark.asyncio
async def test_split_reply_puts_one_footer_on_the_last_message_only(monkeypatch):
    async def fake_build(**_kwargs: Any) -> list[SlackOutboundMessage]:
        return [
            SlackOutboundMessage(
                text="Intro",
                blocks=[{"type": "section", "text": {"type": "mrkdwn", "text": "Intro"}}],
            ),
            SlackOutboundMessage(
                text="Details",
                blocks=[{"type": "section", "text": {"type": "mrkdwn", "text": "Details"}}],
            ),
        ]

    monkeypatch.setattr(
        "apps.tenant_app_service.agent_ingress.slack.markdown_delivery.build_outbound_messages",
        fake_build,
    )
    slack = _SlackStub()
    started, now = _window(90.16)
    await deliver_markdown_to_slack(
        client=slack,
        bot_token="xoxb-test",
        channel_id="C1",
        markdown="Intro",
        message_id="msg_1",
        thread_ts="1.0",
        update_ts="9.0",
        image_fetcher=_no_fetch,
        turn_started_at=started,
        now=now,
    )

    assert len(slack.updates) == 1
    assert len(slack.posts) == 1
    replaced_placeholder = slack.updates[0]
    assert replaced_placeholder["ts"] == "9.0"
    assert _section_text(replaced_placeholder["blocks"]) == "Intro"
    assert _footer_texts(replaced_placeholder["blocks"]) == []
    assert "Took " not in replaced_placeholder["text"]
    assert all(block.get("type") != "actions" for block in replaced_placeholder["blocks"])
    last = slack.posts[0]
    assert _footer_texts(last["blocks"]) == ["Took 1m 30.2s"]
    assert last["text"].endswith("\nTook 1m 30.2s")
    assert "Took 1m 30.2s" not in _section_text(last["blocks"])
    assert last["blocks"][-2]["block_id"] == "feedback_msg_1"


@pytest.mark.asyncio
async def test_block_limit_keeps_footer_on_the_new_last_message(monkeypatch):
    blocks = [{"type": "section", "text": {"type": "mrkdwn", "text": f"line {index}"}} for index in range(49)]

    async def fake_build(**_kwargs: Any) -> list[SlackOutboundMessage]:
        return [SlackOutboundMessage(text="line 0", blocks=list(blocks))]

    monkeypatch.setattr(
        "apps.tenant_app_service.agent_ingress.slack.markdown_delivery.build_outbound_messages",
        fake_build,
    )
    slack = _SlackStub()
    started, now = _window(0.05)
    await deliver_markdown_to_slack(
        client=slack,
        bot_token="xoxb-test",
        channel_id="C1",
        markdown="ignored",
        message_id="msg_1",
        thread_ts=None,
        image_fetcher=_no_fetch,
        turn_started_at=started,
        now=now,
    )

    assert len(slack.posts) == 2
    assert _footer_texts(slack.posts[0]["blocks"]) == []
    assert all(len(message["blocks"]) <= 50 for message in slack.posts)
    assert _footer_texts(slack.posts[1]["blocks"]) == ["Took 0.1s"]
    assert _section_text(slack.posts[1]["blocks"]) == "line 48"
    assert slack.posts[0]["blocks"][-1]["type"] == "section"


@pytest.mark.asyncio
async def test_missing_or_negative_duration_leaves_the_result_unchanged():
    future, now = _window(-5)
    for started in (None, future):
        slack = _SlackStub()
        await deliver_markdown_to_slack(
            client=slack,
            bot_token="xoxb-test",
            channel_id="C1",
            markdown="Still here",
            message_id="msg_1",
            thread_ts=None,
            image_fetcher=_no_fetch,
            turn_started_at=started,
            now=now,
        )
        assert _section_text(slack.posts[0]["blocks"]) == "Still here"
        assert _footer_texts(slack.posts[0]["blocks"]) == []
        assert "Took " not in slack.posts[0]["text"]
        assert slack.posts[0]["blocks"][-1]["type"] == "actions"


@pytest.mark.asyncio
async def test_failure_and_empty_fallback_keep_their_text_and_add_a_footer():
    started, now = _window(0.04)
    cases = [
        slack_user_message(SlackMessageKey.CHAT_GENERIC_FAILURE),
        SLACK_EMPTY_REPLY_FALLBACK,
    ]
    for body in cases:
        slack = _SlackStub()
        await deliver_markdown_to_slack(
            client=slack,
            bot_token="xoxb-test",
            channel_id="D1",
            markdown=body,
            message_id=None,
            thread_ts=None,
            image_fetcher=_no_fetch,
            turn_started_at=started,
            now=now,
        )
        assert _section_text(slack.posts[0]["blocks"]) == body
        assert _footer_texts(slack.posts[0]["blocks"]) == ["Took <0.1s"]


@pytest.mark.asyncio
async def test_plain_text_fallback_keeps_footer_on_its_own_line():
    slack = _SlackStub(reject_times=2)
    started, now = _window(119.96)
    await deliver_markdown_to_slack(
        client=slack,
        bot_token="xoxb-test",
        channel_id="C1",
        markdown="Hello from the model",
        message_id="msg_1",
        thread_ts=None,
        image_fetcher=_no_fetch,
        turn_started_at=started,
        now=now,
    )

    posted = slack.posts[0]
    assert posted["text"] == "Hello from the model\nTook 2m 0.0s"
    assert _footer_texts(posted["blocks"]) == []
    assert posted["blocks"][-1]["type"] == "actions"


@pytest.mark.asyncio
async def test_two_deliveries_do_not_share_a_running_total():
    first_start, first_end = _window(90.16)
    second_end = first_end + timedelta(seconds=12.34)
    second_start = second_end - timedelta(seconds=12.34)
    seen: list[str] = []
    for started, now in ((first_start, first_end), (second_start, second_end)):
        slack = _SlackStub()
        await deliver_markdown_to_slack(
            client=slack,
            bot_token="xoxb-test",
            channel_id="C1",
            markdown="Answer",
            message_id=None,
            thread_ts="thread",
            image_fetcher=_no_fetch,
            turn_started_at=started,
            now=now,
        )
        seen.append(_footer_texts(slack.posts[0]["blocks"])[0])
    assert seen == ["Took 1m 30.2s", "Took 12.3s"]


def _message_event(**kwargs: Any) -> SlackMessageEvent:
    defaults = {
        "event_id": "Ev1",
        "team_id": "T1",
        "user_id": "U1",
        "channel_id": "D123",
        "text": "hi",
        "ts": "1700000000.000100",
        "channel_type": "im",
        "source": "dm",
    }
    defaults.update(kwargs)
    return SlackMessageEvent(**defaults)


@pytest.mark.asyncio
async def test_ingress_passes_turn_start_from_chat_turn_result():
    endpoint = MagicMock()
    endpoint.id = 1
    endpoint.tenant_id = 2
    endpoint.enabled = True
    endpoint.agent_id = 1
    started = datetime(2026, 1, 1, tzinfo=UTC)

    async def _run(run_id: str | None, turn_started_at: datetime | None) -> Any:
        db = MagicMock()
        db.commit = AsyncMock()
        service = SlackIngressService(db=db)
        service.repo = MagicMock()
        service.repo.decrypt_bot_token = MagicMock(return_value="xoxb-test")
        service.client = MagicMock()
        service.client.chat_post_message = AsyncMock(return_value={"ts": "1.0"})
        service.client.chat_post_ephemeral = AsyncMock()
        service.identity_service = MagicMock()
        bind_result = MagicMock()
        bind_result.action = "allow"
        bind_result.user_id = 4
        bind_result.reason = None
        service.identity_service.resolve_slack_user = AsyncMock(return_value=bind_result)
        service.token_issuer = MagicMock()
        service.token_issuer.issue = MagicMock(return_value="token")
        posted = AsyncMock()
        with (
            patch(
                "apps.tenant_app_service.agent_ingress.slack.ingress_service.is_eligible_slack_identity",
                return_value=True,
            ),
            patch(
                "apps.tenant_app_service.agent_ingress.slack.ingress_service.user_has_chat_access",
                new=AsyncMock(return_value=True),
            ),
            patch.object(service, "_get_endpoint", new=AsyncMock(return_value=endpoint)),
            patch.object(service, "_resolve_thread_id", new=AsyncMock(return_value=("2_4_1_new", 1))),
            patch.object(
                service,
                "_build_user_dto",
                new=AsyncMock(return_value=(MagicMock(id=4, username="u", role="admin"), "T")),
            ),
            patch(
                "apps.tenant_app_service.agent_ingress.slack.ingress_service.run_slack_chat_turn",
                new=AsyncMock(
                    return_value=MagicMock(
                        message_id="m1",
                        session_id="s1",
                        thinking_ts="1.0",
                        reply_text="ok",
                        run_id=run_id,
                        turn_started_at=turn_started_at,
                    )
                ),
            ),
            patch(
                "apps.tenant_app_service.agent_ingress.slack.ingress_service.post_slack_reply_with_feedback",
                new=posted,
            ),
            patch(
                "apps.tenant_app_service.agent_ingress.slack.ingress_service.resolve_feedback_message_id",
                new=AsyncMock(return_value="m1"),
            ),
            patch(
                "apps.tenant_app_service.chat.application.runs.thread_run_service.ThreadRunService.is_run_cancelled",
                new=AsyncMock(return_value=False),
            ),
        ):
            await service.handle_message(_message_event(), endpoint_id=1)
        return posted

    posted = await _run(None, None)
    assert posted.await_args.kwargs["turn_started_at"] is None

    posted = await _run("run-1", started)
    assert posted.await_args.kwargs["turn_started_at"] == started
    assert posted.await_args.kwargs["text"] == "ok"


@pytest.mark.asyncio
async def test_thread_busy_notice_has_no_duration_footer():
    from apps.shared.core.exceptions import ThreadBusyError

    endpoint = MagicMock()
    endpoint.id = 1
    endpoint.tenant_id = 2
    endpoint.enabled = True
    endpoint.agent_id = 1
    db = MagicMock()
    db.commit = AsyncMock()
    service = SlackIngressService(db=db)
    service.repo = MagicMock()
    service.repo.decrypt_bot_token = MagicMock(return_value="xoxb-test")
    service.client = MagicMock()
    service.client.chat_post_ephemeral = AsyncMock()
    service.identity_service = MagicMock()
    bind_result = MagicMock(action="allow", user_id=4, reason=None)
    service.identity_service.resolve_slack_user = AsyncMock(return_value=bind_result)
    service.token_issuer = MagicMock()
    service.token_issuer.issue = MagicMock(return_value="token")
    posted = AsyncMock()

    with (
        patch(
            "apps.tenant_app_service.agent_ingress.slack.ingress_service.is_eligible_slack_identity",
            return_value=True,
        ),
        patch(
            "apps.tenant_app_service.agent_ingress.slack.ingress_service.user_has_chat_access",
            new=AsyncMock(return_value=True),
        ),
        patch.object(service, "_get_endpoint", new=AsyncMock(return_value=endpoint)),
        patch.object(service, "_resolve_thread_id", new=AsyncMock(return_value=("thread", 1))),
        patch.object(
            service,
            "_build_user_dto",
            new=AsyncMock(return_value=(MagicMock(id=4, username="u", role="admin"), "T")),
        ),
        patch(
            "apps.tenant_app_service.agent_ingress.slack.ingress_service.run_slack_chat_turn",
            new=AsyncMock(side_effect=ThreadBusyError("busy")),
        ),
        patch(
            "apps.tenant_app_service.agent_ingress.slack.ingress_service.post_slack_reply_with_feedback",
            new=posted,
        ),
    ):
        await service.handle_message(_message_event(), endpoint_id=1)

    posted.assert_not_awaited()
    notice = service.client.chat_post_ephemeral.await_args.kwargs["text"]
    assert notice == slack_user_message(SlackMessageKey.THREAD_BUSY)
    assert "Took " not in notice
