"""Deliver a finished agent Markdown reply to Slack.

Rendering stays in ``markdown_blocks``. Private images upload once via
``SlackAssetResolver`` for both Block Kit and Canvas. Canvas creation runs
only after the agent reply is complete.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from slack_sdk.errors import SlackApiError
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.utils.logger import get_logger
from apps.tenant_app_service.agent_ingress.slack.client import SlackClientPort, _slack_response_dict
from apps.tenant_app_service.agent_ingress.slack.domain import (
    ensure_slack_reply_text,
    format_reply_for_slack,
    split_long_text,
)
from apps.tenant_app_service.agent_ingress.slack.feedback_blocks import append_feedback_actions
from apps.tenant_app_service.agent_ingress.slack.markdown_blocks import (
    RenderRoute,
    SlackMarkdownPlan,
    SlackMarkdownPolicy,
    canvas_summary_blocks,
    canvas_truncation_context,
    message_text,
    plan_slack_markdown,
    split_blocks,
)
from apps.tenant_app_service.agent_ingress.slack.slack_asset_resolver import SlackAssetResolver
from apps.tenant_app_service.agent_ingress.slack.slack_image_fetcher import (
    ImageFetcher,
    default_image_fetcher,
    make_slack_image_fetcher,
)

logger = get_logger(__name__)

CANVAS_MARKDOWN_MAX_CHARS = 1_048_576
_DEBUG_MARKDOWN_CHARS = 2000


class CanvasAccessError(Exception):
    """Raised when a Canvas cannot be shared with the conversation."""


@dataclass(frozen=True)
class SlackOutboundMessage:
    """One chat.postMessage / chat.update payload, without feedback actions."""

    text: str
    blocks: list[dict[str, Any]]


def _select_image_fetcher(
    *,
    db_session: AsyncSession | None,
    tenant_id: int | None,
    requester_user_id: int | None,
    requester_role: str | None,
    image_fetcher: ImageFetcher | None,
) -> ImageFetcher:
    if image_fetcher is not None:
        return image_fetcher
    if db_session is not None and tenant_id is not None and requester_user_id is not None and requester_role:
        return make_slack_image_fetcher(
            db=db_session,
            tenant_id=tenant_id,
            user_id=requester_user_id,
            user_role=requester_role,
        )
    return default_image_fetcher


async def deliver_markdown_to_slack(
    *,
    client: SlackClientPort,
    bot_token: str,
    channel_id: str,
    markdown: str,
    message_id: str | None,
    thread_ts: str | None,
    update_ts: str | None = None,
    portal_origin: str | None = None,
    api_origin: str | None = None,
    slack_user_id: str | None = None,
    channel_type: str | None = None,
    policy: SlackMarkdownPolicy | None = None,
    image_fetcher: ImageFetcher | None = None,
    db_session: AsyncSession | None = None,
    tenant_id: int | None = None,
    requester_user_id: int | None = None,
    requester_role: str | None = None,
    agent_id: int | None = None,
) -> str | None:
    """Render Markdown and post it. A block rejection retries once as mrkdwn."""
    active = policy or SlackMarkdownPolicy()
    source = ensure_slack_reply_text(markdown)
    _ = agent_id  # reserved for delivery metadata; authz uses requester ACL only
    fetcher = _select_image_fetcher(
        db_session=db_session,
        tenant_id=tenant_id,
        requester_user_id=requester_user_id,
        requester_role=requester_role,
        image_fetcher=image_fetcher,
    )
    messages = await build_outbound_messages(
        client=client,
        bot_token=bot_token,
        channel_id=channel_id,
        markdown=source,
        thread_ts=thread_ts,
        portal_origin=portal_origin,
        api_origin=api_origin,
        slack_user_id=slack_user_id,
        channel_type=channel_type,
        policy=active,
        image_fetcher=fetcher,
    )
    try:
        return await _send_messages(
            client=client,
            bot_token=bot_token,
            channel_id=channel_id,
            messages=messages,
            message_id=message_id,
            thread_ts=thread_ts,
            update_ts=update_ts,
        )
    except SlackApiError as exc:
        if not _is_invalid_blocks(exc):
            raise
        detail = _slack_response_dict(exc)
        logger.warning(
            "Slack rejected blocks (%s); falling back to mrkdwn. "
            "Inline chart images need files:read + files:write on the bot token.",
            detail.get("error") or detail,
        )
        fallback = degraded_outbound_messages(
            source,
            portal_origin=portal_origin,
            api_origin=api_origin,
            policy=active,
        )
        return await _send_messages(
            client=client,
            bot_token=bot_token,
            channel_id=channel_id,
            messages=fallback,
            message_id=message_id,
            thread_ts=thread_ts,
            update_ts=update_ts,
        )


async def build_outbound_messages(
    *,
    client: SlackClientPort,
    bot_token: str,
    channel_id: str,
    markdown: str,
    thread_ts: str | None,
    portal_origin: str | None,
    api_origin: str | None,
    slack_user_id: str | None,
    channel_type: str | None,
    policy: SlackMarkdownPolicy,
    image_fetcher: ImageFetcher,
) -> list[SlackOutboundMessage]:
    """Turn Markdown into one or more Slack messages."""
    plan = plan_slack_markdown(
        markdown,
        policy=policy,
        portal_origin=portal_origin,
        api_origin=api_origin,
    )
    resolver = SlackAssetResolver(client=client, bot_token=bot_token, image_fetcher=image_fetcher)
    delivered_route = plan.route
    reason = plan.degrade_reason
    if plan.route == RenderRoute.DEGRADED:
        messages = degraded_outbound_messages(
            markdown,
            portal_origin=portal_origin,
            api_origin=api_origin,
            policy=policy,
        )
    elif plan.route == RenderRoute.CANVAS:
        canvas_markdown = await resolver.prepare_canvas_markdown(
            markdown,
            portal_origin=portal_origin,
            api_origin=api_origin,
        )
        canvas_url = await _try_canvas(
            client=client,
            bot_token=bot_token,
            channel_id=channel_id,
            channel_type=channel_type,
            slack_user_id=slack_user_id,
            markdown=canvas_markdown,
            plan=plan,
        )
        if canvas_url:
            blocks = canvas_summary_blocks(plan, canvas_url, policy)
            messages = [_outbound(blocks)]
        else:
            delivered_route = RenderRoute.DEGRADED
            reason = "canvas_failed"
            messages = degraded_outbound_messages(
                markdown,
                portal_origin=portal_origin,
                api_origin=api_origin,
                policy=policy,
            )
    else:
        blocks = await resolver.resolve_blocks(plan.blocks)
        if plan.truncated_cells:
            canvas_markdown = await resolver.prepare_canvas_markdown(
                markdown,
                portal_origin=portal_origin,
                api_origin=api_origin,
            )
            canvas_url = await _try_canvas(
                client=client,
                bot_token=bot_token,
                channel_id=channel_id,
                channel_type=channel_type,
                slack_user_id=slack_user_id,
                markdown=canvas_markdown,
                plan=plan,
            )
            if canvas_url:
                blocks = [*blocks, canvas_truncation_context(canvas_url)]
            else:
                reason = "canvas_failed"
        messages = [_outbound(chunk) for chunk in split_blocks(blocks, policy.max_blocks)]

    if not messages:
        delivered_route = RenderRoute.DEGRADED
        reason = reason or "empty"
        messages = degraded_outbound_messages(
            markdown,
            portal_origin=portal_origin,
            api_origin=api_origin,
            policy=policy,
        )
    _log_plan(plan, messages, thread_ts, delivered_route, reason)
    return messages


def degraded_outbound_messages(
    markdown: str,
    *,
    portal_origin: str | None,
    api_origin: str | None,
    policy: SlackMarkdownPolicy,
) -> list[SlackOutboundMessage]:
    """Fall back to the existing mrkdwn formatter, one section per chunk."""
    formatted = ensure_slack_reply_text(
        format_reply_for_slack(markdown, portal_origin=portal_origin, api_origin=api_origin)
    )
    chunks = [chunk for chunk in split_long_text(formatted, max_length=policy.section_max_chars) if chunk.strip()]
    if not chunks:
        chunks = [formatted]
    return [
        SlackOutboundMessage(
            text=chunk,
            blocks=[{"type": "section", "text": {"type": "mrkdwn", "text": chunk}}],
        )
        for chunk in chunks
    ]


async def _try_canvas(
    *,
    client: SlackClientPort,
    bot_token: str,
    channel_id: str,
    channel_type: str | None,
    slack_user_id: str | None,
    markdown: str,
    plan: SlackMarkdownPlan,
) -> str | None:
    if len(markdown) > CANVAS_MARKDOWN_MAX_CHARS:
        logger.warning("Slack canvas skipped: markdown exceeds 1 MiB")
        return None
    try:
        access_channel, access_user = _canvas_access_target(
            channel_id=channel_id,
            channel_type=channel_type,
            slack_user_id=slack_user_id,
        )
        title = _canvas_title(plan)
        canvas_id = await client.create_canvas(bot_token=bot_token, title=title, markdown=markdown)
        await client.grant_canvas_read(
            bot_token=bot_token,
            canvas_id=canvas_id,
            channel_id=access_channel,
            user_id=access_user,
        )
        return await client.canvas_permalink(bot_token=bot_token, canvas_id=canvas_id)
    except Exception as exc:
        logger.warning("Slack canvas fallback: %s", exc)
        return None


def _canvas_access_target(
    *,
    channel_id: str,
    channel_type: str | None,
    slack_user_id: str | None,
) -> tuple[str | None, str | None]:
    """Return the single canvases.access.set target for this conversation."""
    direct = channel_type in {"im", "mpim"} or channel_id.startswith("D")
    if direct:
        if not slack_user_id:
            raise CanvasAccessError("direct message canvas requires a Slack user id")
        return None, slack_user_id
    if not channel_id:
        raise CanvasAccessError("canvas access target missing")
    return channel_id, None


def _canvas_title(plan: SlackMarkdownPlan) -> str:
    raw = " ".join((plan.summary_title or "Agent reply").split())
    return raw[:120] or "Agent reply"


def _outbound(blocks: list[dict[str, Any]]) -> SlackOutboundMessage:
    return SlackOutboundMessage(text=ensure_slack_reply_text(message_text(blocks)), blocks=blocks)


def _log_plan(
    plan: SlackMarkdownPlan,
    messages: list[SlackOutboundMessage],
    thread_ts: str | None,
    delivered_route: RenderRoute,
    reason: str | None,
) -> None:
    block_types = [block.get("type") for message in messages for block in message.blocks]
    logger.info(
        "Slack markdown delivery route=%s delivered=%s table_rows=%s images=%s blocks=%s reason=%s thread_ts=%s",
        plan.route,
        delivered_route,
        plan.table_data_rows,
        plan.image_count,
        len(block_types),
        reason,
        thread_ts,
    )
    logger.debug(
        "Slack markdown delivery nodes=%s block_types=%s markdown=%s",
        plan.node_counts,
        block_types,
        (plan.markdown or "")[:_DEBUG_MARKDOWN_CHARS],
    )


def _is_invalid_blocks(exc: SlackApiError) -> bool:
    response = exc.response
    if isinstance(response, dict):
        return response.get("error") == "invalid_blocks"
    getter = getattr(response, "get", None)
    if getter is None:
        return False
    return getter("error") == "invalid_blocks"


async def _send_messages(
    *,
    client: SlackClientPort,
    bot_token: str,
    channel_id: str,
    messages: list[SlackOutboundMessage],
    message_id: str | None,
    thread_ts: str | None,
    update_ts: str | None,
) -> str | None:
    posted_ts: str | None = None
    pending_update_ts = update_ts
    last_index = len(messages) - 1
    for index, message in enumerate(messages):
        blocks: list[dict[str, Any]] | None = message.blocks
        if message_id and index == last_index:
            blocks = append_feedback_actions(message.blocks, message_id)
        if not blocks:
            blocks = None
        if pending_update_ts:
            await client.chat_update(
                bot_token=bot_token,
                channel=channel_id,
                ts=pending_update_ts,
                text=message.text,
                blocks=blocks,
            )
            posted_ts = pending_update_ts
            pending_update_ts = None
        else:
            post_result = await client.chat_post_message(
                bot_token=bot_token,
                channel=channel_id,
                text=message.text,
                thread_ts=thread_ts,
                blocks=blocks,
            )
            posted_ts = post_result.get("ts") if post_result else posted_ts
    return posted_ts
