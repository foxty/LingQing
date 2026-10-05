"""Domain layer for Slack channel adapter.

Pure business logic: Slack signature verification, event classification,
conversation key derivation, bind decision inputs. No framework or DB imports.
"""

from __future__ import annotations

import enum
import hashlib
import hmac
import re
import time
from dataclasses import dataclass

from apps.tenant_app_service.agent_ingress.slack.messages import (
    SLACK_EMPTY_REPLY_FALLBACK,
)

SLACK_SIGNATURE_MAX_AGE_SECONDS = 60 * 5  # 5 minutes


class SlackEventType(enum.StrEnum):
    """Slack Events API event types we care about."""

    URL_VERIFICATION = "url_verification"
    MESSAGE = "message"
    APP_MENTION = "app_mention"


SHARED_CHANNEL_TYPES: frozenset[str] = frozenset({"channel", "group", "mpim"})


@dataclass(frozen=True)
class ConversationKey:
    """Stable composite key for a Slack conversation mapping."""

    tenant_id: int
    slack_channel_id: str
    slack_thread_ts: str = ""

    def composite(self) -> tuple[int, str, str]:
        return (self.tenant_id, self.slack_channel_id, self.slack_thread_ts)


@dataclass(frozen=True)
class SlackMessageEvent:
    """Normalized Slack message payload we act on."""

    event_id: str
    team_id: str
    user_id: str
    channel_id: str
    text: str
    ts: str
    thread_ts: str | None = None
    channel_type: str | None = None
    source: str = "dm"
    bot_user_id: str | None = None


def verify_slack_signature(
    *,
    signing_secret: str,
    timestamp: str,
    body: str,
    signature: str,
    now: float | None = None,
    max_age_seconds: int = SLACK_SIGNATURE_MAX_AGE_SECONDS,
) -> bool:
    """Verify the X-Slack-Signature header against the raw request body.

    Slack computes: HMAC_SHA256(signing_secret, f"v0:{ts}:{body}"), prefixed with "v0=".
    Reject if the timestamp is older than max_age_seconds.
    """
    if not signing_secret or not timestamp or not body or not signature:
        return False

    try:
        ts_int = int(timestamp)
    except (TypeError, ValueError):
        return False

    current = now if now is not None else time.time()
    if abs(current - ts_int) > max_age_seconds:
        return False

    base = f"v0:{timestamp}:{body}"
    computed = "v0=" + hmac.new(
        signing_secret.encode("utf-8"), base.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(computed, signature)


def slack_signature_failure_reason(
    *,
    signing_secret: str,
    timestamp: str,
    body: str,
    signature: str,
    now: float | None = None,
    max_age_seconds: int = SLACK_SIGNATURE_MAX_AGE_SECONDS,
) -> str | None:
    """Return a stable failure reason, or None when the signature would verify."""
    if not signing_secret:
        return "missing_signing_secret"
    if not timestamp:
        return "missing_timestamp_header"
    if not signature:
        return "missing_signature_header"
    if not body:
        return "empty_body"
    try:
        ts_int = int(timestamp)
    except (TypeError, ValueError):
        return "invalid_timestamp_header"
    current = now if now is not None else time.time()
    age_seconds = abs(current - ts_int)
    if age_seconds > max_age_seconds:
        return f"timestamp_expired age_seconds={int(age_seconds)} max_age_seconds={max_age_seconds}"
    if not verify_slack_signature(
        signing_secret=signing_secret,
        timestamp=timestamp,
        body=body,
        signature=signature,
        now=now,
        max_age_seconds=max_age_seconds,
    ):
        return "signature_mismatch"
    return None


def describe_ignored_event(event: dict) -> str:
    """Stable reason string when no Slack ingress parser accepts an event."""
    if not isinstance(event, dict):
        return "event_not_object"
    event_type = event.get("type") or "unknown"
    if event_type == "app_mention":
        if not is_processable_message_event(event):
            return _describe_unprocessable_message(event, event_type)
        if not (event.get("user") and event.get("channel") and event.get("ts")):
            return "missing_user_channel_or_ts"
        return f"unhandled type={event_type}"
    if event_type == "message":
        if parse_message_event(event) is not None:
            return "unexpected_accepted_dm"
        if event.get("thread_ts") and parse_thread_reply_event(event) is not None:
            return "unexpected_accepted_thread_reply"
        return _describe_unprocessable_message(event, event_type)
    return f"unhandled type={event_type}"


def _describe_unprocessable_message(event: dict, event_type: str) -> str:
    subtype = event.get("subtype")
    channel_type = event.get("channel_type")
    if event.get("bot_id") or subtype == "bot_message":
        return f"bot_message type={event_type}"
    if subtype in {"message_changed", "message_deleted", "message_replies"}:
        return f"unsupported_subtype={subtype}"
    text = event.get("text") or ""
    if not text.strip():
        return f"empty_text type={event_type} subtype={subtype or 'none'}"
    if event_type == "message" and channel_type and channel_type != "im":
        if not event.get("thread_ts"):
            return f"non_dm_channel_type={channel_type}"
        if channel_type not in SHARED_CHANNEL_TYPES:
            return f"unsupported_channel_type={channel_type}"
        return "thread_reply_no_text"
    if not (event.get("user") and event.get("channel") and event.get("ts")):
        return "missing_user_channel_or_ts"
    return f"unhandled type={event_type} subtype={subtype or 'none'} channel_type={channel_type or 'none'}"


def is_processable_message_event(event: dict) -> bool:
    """True if this Slack event is a DM message we should hand to the agent.

    Filters out:
      - bot messages (bot_id / subtype=bot_message) to prevent loops
      - message_changed / message_deleted / message_replies subtypes
      - empty text / file-only messages (MVP)
    """
    if not isinstance(event, dict):
        return False
    if event.get("bot_id") or event.get("subtype") == "bot_message":
        return False
    subtype = event.get("subtype")
    if subtype in {"message_changed", "message_deleted", "message_replies"}:
        return False
    text = event.get("text") or ""
    if not text.strip():
        return False
    return True


def parse_message_event(event: dict, event_id: str | None = None) -> SlackMessageEvent | None:
    """Extract a SlackMessageEvent from a Slack event payload, or None if not a DM.

    Only DMs (channel_type == "im") are accepted in MVP.
    """
    if not is_processable_message_event(event):
        return None
    if event.get("channel_type") and event["channel_type"] != "im":
        return None
    team_id = event.get("team") or ""
    user_id = event.get("user") or ""
    channel_id = event.get("channel") or ""
    text = event.get("text") or ""
    ts = event.get("ts") or ""
    if not (user_id and channel_id and ts):
        return None
    return SlackMessageEvent(
        event_id=event_id or event.get("event_id") or ts,
        team_id=team_id,
        user_id=user_id,
        channel_id=channel_id,
        text=text,
        ts=ts,
        thread_ts=event.get("thread_ts"),
        channel_type=event.get("channel_type"),
        source="dm",
    )


def parse_app_mention_event(event: dict, event_id: str | None = None) -> SlackMessageEvent | None:
    """Extract a SlackMessageEvent from an app_mention payload."""
    if event.get("type") != SlackEventType.APP_MENTION:
        return None
    if not is_processable_message_event(event):
        return None
    user_id = event.get("user") or ""
    channel_id = event.get("channel") or ""
    text = event.get("text") or ""
    ts = event.get("ts") or ""
    if not (user_id and channel_id and ts):
        return None
    return SlackMessageEvent(
        event_id=event_id or event.get("event_id") or ts,
        team_id=event.get("team") or "",
        user_id=user_id,
        channel_id=channel_id,
        text=text,
        ts=ts,
        thread_ts=event.get("thread_ts"),
        channel_type=event.get("channel_type"),
        source="app_mention",
    )


def parse_thread_reply_event(event: dict, event_id: str | None = None) -> SlackMessageEvent | None:
    """Extract a SlackMessageEvent from a channel/group/mpim thread follow-up."""
    if event.get("type") != SlackEventType.MESSAGE:
        return None
    if not is_processable_message_event(event):
        return None
    channel_type = event.get("channel_type")
    thread_ts = event.get("thread_ts")
    if not thread_ts or channel_type not in SHARED_CHANNEL_TYPES:
        return None
    user_id = event.get("user") or ""
    channel_id = event.get("channel") or ""
    text = event.get("text") or ""
    ts = event.get("ts") or ""
    if not (user_id and channel_id and ts):
        return None
    return SlackMessageEvent(
        event_id=event_id or event.get("event_id") or ts,
        team_id=event.get("team") or "",
        user_id=user_id,
        channel_id=channel_id,
        text=text,
        ts=ts,
        thread_ts=thread_ts,
        channel_type=channel_type,
        source="thread_reply",
    )


_BOT_MENTION_PATTERN = re.compile(r"^<@[A-Z0-9]+>\s*")


def strip_bot_mention(text: str, bot_user_id: str | None = None) -> str:
    """Remove leading bot @mention markup from message text."""
    stripped = _BOT_MENTION_PATTERN.sub("", text).strip()
    if bot_user_id:
        explicit = f"<@{bot_user_id}>"
        if stripped.startswith(explicit):
            stripped = stripped[len(explicit) :].strip()
    return stripped


def slack_mapping_thread_ts(event: SlackMessageEvent) -> str:
    """Thread root ts used as the conversation mapping key."""
    if event.channel_type == "im":
        return ""
    return slack_thread_root_ts(thread_ts=event.thread_ts, message_ts=event.ts)


def slack_thread_root_ts(*, thread_ts: str | None, message_ts: str) -> str:
    """Root timestamp of a Slack conversation thread.

    For channel @mentions this is the parent message ts; for thread replies it
    is the existing thread_ts. Used as part of the agent-thread mapping key.
    """
    return thread_ts or message_ts


def slack_reply_thread_ts(
    *,
    channel_type: str | None,
    thread_ts: str | None,
    message_ts: str,
) -> str | None:
    """Slack thread_ts for bot replies.

    DMs use flat replies unless the user is already in a Slack thread.
    Shared channels always reply in-thread under the conversation root.
    """
    if channel_type == "im":
        return thread_ts
    return slack_thread_root_ts(thread_ts=thread_ts, message_ts=message_ts)


def conversation_key(
    tenant_id: int,
    slack_channel_id: str,
    slack_thread_ts: str = "",
) -> ConversationKey:
    """Build the stable conversation key for thread mapping."""
    return ConversationKey(
        tenant_id=tenant_id,
        slack_channel_id=slack_channel_id,
        slack_thread_ts=slack_thread_ts,
    )


def split_long_text(text: str, max_length: int = 4000) -> list[str]:
    """Split text into chunks under Slack's 4000 char message limit.

    Splits on newlines first to preserve readability, then hard-splits long lines.
    """
    if len(text) <= max_length:
        return [text]
    chunks: list[str] = []
    for line in text.split("\n"):
        while len(line) > max_length:
            chunks.append(line[:max_length])
            line = line[max_length:]
        chunks.append(line)
    # Re-glue small lines back together to avoid message explosion
    merged: list[str] = []
    buffer = ""
    for chunk in chunks:
        candidate = buffer + ("\n" if buffer else "") + chunk
        if len(candidate) <= max_length:
            buffer = candidate
        else:
            if buffer:
                merged.append(buffer)
            buffer = chunk
    if buffer:
        merged.append(buffer)
    return merged


_CODE_PLACEHOLDER = "\x00SLACK_CODE_{}\x00"
_LINK_PLACEHOLDER = "\x00SLACK_LINK_{}\x00"
_LINK_PATTERN = re.compile(r"(?<!!)\[([^\]]+)\]\(([^)]+)\)")
_IMAGE_PATTERN = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
_BROKEN_IMAGE_LINK_PATTERN = re.compile(r"!(?:<)?([^|>]+)\|([^>]+)>")
_SLACK_RELATIVE_LINK_PATTERN = re.compile(r"<(/[^|>]+)\|([^>]+)>")
_HEADER_PATTERN = re.compile(r"^#{1,6}\s+(.+)$", re.MULTILINE)
_BOLD_PATTERN = re.compile(r"\*\*(.+?)\*\*|__(.+?)__")
_TABLE_ROW_PATTERN = re.compile(r"^\|[\s\-:|]+\|$")
_CODE_FENCE_PATTERN = re.compile(r"```[\s\S]*?```|`[^`\n]+`")
_EMOJI_SHORTCODE_PATTERN = re.compile(r":([a-z0-9_+-]+):")

# Common agent emoji shortcodes → unicode (Slack shortcodes are unreliable in all clients).
_EMOJI_SHORTCODE_MAP: dict[str, str] = {
    "white_check_mark": "✅",
    "chart_with_downwards_trend": "📉",
    "chart_with_upwards_trend": "📈",
    "date": "📅",
    "department_store": "🏬",
    "earth_asia": "🌏",
    "page_facing_up": "📄",
    "bar_chart": "📊",
    "warning": "⚠️",
    "x": "❌",
}


def format_reply_for_slack(
    text: str,
    *,
    portal_origin: str | None = None,
    api_origin: str | None = None,
) -> str:
    """Convert agent markdown into Slack mrkdwn for chat.postMessage.

    Resolves relative report/chart links to absolute URLs and converts markdown
    images into labeled chart links Slack can click.
    """
    if not text or not text.strip():
        return text

    converted = _BROKEN_IMAGE_LINK_PATTERN.sub(
        lambda m: _chart_slack_link(m.group(1), m.group(2), portal_origin, api_origin),
        text,
    )
    protected, code_spans = _protect_code_spans(converted)
    protected, link_spans = _convert_images_and_links(protected, portal_origin, api_origin)
    converted = _HEADER_PATTERN.sub(r"*\1*", protected)
    converted = _BOLD_PATTERN.sub(lambda m: f"*{m.group(1) or m.group(2)}*", converted)
    converted = _simplify_markdown_tables(converted)
    converted = _restore_link_spans(converted, link_spans)
    converted = _restore_code_spans(converted, code_spans)
    return _replace_emoji_shortcodes(converted)


def _convert_images_and_links(
    text: str,
    portal_origin: str | None,
    api_origin: str | None,
) -> tuple[str, list[str]]:
    link_spans: list[str] = []

    def _store_link(link_text: str) -> str:
        link_spans.append(link_text)
        return _LINK_PLACEHOLDER.format(len(link_spans) - 1)

    text = _IMAGE_PATTERN.sub(
        lambda m: _store_link(_chart_slack_link(m.group(2), m.group(1) or "Chart", portal_origin, api_origin)),
        text,
    )
    text = _LINK_PATTERN.sub(
        lambda m: _store_link(
            _slack_link(_resolve_url(m.group(2), portal_origin, api_origin), m.group(1))
        ),
        text,
    )
    text = _SLACK_RELATIVE_LINK_PATTERN.sub(
        lambda m: _store_link(
            _slack_link(_resolve_url(m.group(1), portal_origin, api_origin), m.group(2))
        ),
        text,
    )
    return text, link_spans


def _chart_slack_link(
    url: str,
    label: str,
    portal_origin: str | None,
    api_origin: str | None,
) -> str:
    resolved = _resolve_url(url, portal_origin, api_origin)
    title = label.strip() or "Chart"
    return f"📊 {_slack_link(resolved, title)}"


def _slack_link(url: str, label: str) -> str:
    return f"<{url}|{label}>"


def _resolve_url(url: str, portal_origin: str | None, api_origin: str | None) -> str:
    cleaned = url.strip()
    if cleaned.startswith(("http://", "https://")):
        return _rewrite_localhost_origin(cleaned, api_origin, portal_origin)
    if cleaned.startswith("/reports"):
        return _join_origin(portal_origin, cleaned)
    if cleaned.startswith(("/static/", "/api/static/", "/api/")):
        path = cleaned.removeprefix("/api") if cleaned.startswith("/api/") else cleaned
        return _join_origin(api_origin, path)
    return cleaned


def _join_origin(origin: str | None, path: str) -> str:
    if not origin:
        return path
    return f"{origin.rstrip('/')}{path}"


def _rewrite_localhost_origin(url: str, api_origin: str | None, portal_origin: str | None) -> str:
    for local_origin in ("http://localhost:8000", "http://127.0.0.1:8000"):
        if url.startswith(local_origin) and api_origin:
            return url.replace(local_origin, api_origin.rstrip("/"), 1)
    for local_origin in ("http://localhost:5173", "http://127.0.0.1:5173"):
        if url.startswith(local_origin) and portal_origin:
            return url.replace(local_origin, portal_origin.rstrip("/"), 1)
    return url


def _replace_emoji_shortcodes(text: str) -> str:
    def _replace(match: re.Match[str]) -> str:
        name = match.group(1)
        return _EMOJI_SHORTCODE_MAP.get(name, match.group(0))

    return _EMOJI_SHORTCODE_PATTERN.sub(_replace, text)


def _restore_link_spans(text: str, link_spans: list[str]) -> str:
    for index, original in enumerate(link_spans):
        text = text.replace(_LINK_PLACEHOLDER.format(index), original)
    return text


def _protect_code_spans(text: str) -> tuple[str, list[str]]:
    code_spans: list[str] = []

    def _replace(match: re.Match[str]) -> str:
        code_spans.append(match.group(0))
        return _CODE_PLACEHOLDER.format(len(code_spans) - 1)

    return _CODE_FENCE_PATTERN.sub(_replace, text), code_spans


def _restore_code_spans(text: str, code_spans: list[str]) -> str:
    for index, original in enumerate(code_spans):
        text = text.replace(_CODE_PLACEHOLDER.format(index), original)
    return text


def _simplify_markdown_tables(text: str) -> str:
    """Turn markdown table rows into bullet lines Slack can read."""
    lines: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not (stripped.startswith("|") and stripped.endswith("|")):
            lines.append(line)
            continue
        if _TABLE_ROW_PATTERN.match(stripped):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|") if cell.strip()]
        if cells:
            lines.append(f"• {' · '.join(cells)}")
    return "\n".join(lines)


SLACK_BOT_SCOPES: tuple[str, ...] = (
    "chat:write",
    "im:history",
    "users:read",
    "users:read.email",
    "app_mentions:read",
    "channels:history",
    "groups:history",
    "mpim:history",
    "channels:read",
    "groups:read",
)

SLACK_BOT_EVENTS: tuple[str, ...] = (
    "message.im",
    "app_mention",
    "message.channels",
    "message.groups",
    "message.mpim",
)

def ensure_slack_reply_text(text: str, *, fallback: str = SLACK_EMPTY_REPLY_FALLBACK) -> str:
    """Ensure Slack post/update payloads always include non-empty text."""
    cleaned = text.strip()
    return cleaned if cleaned else fallback

DEFAULT_MANIFEST_APP_NAME = "LingQing Agent"
DEFAULT_MANIFEST_BOT_DISPLAY_NAME = "LingQing"


def slack_endpoint_scope_key(*, team_id: str | None, app_id: str | None, tenant_id: int) -> str:
    """Stable external_scope_key for an agent ingress endpoint."""
    if team_id and app_id:
        return f"slack:{team_id}:{app_id}"
    scope = team_id or f"tenant:{tenant_id}"
    return f"slack:{scope}"


def slack_auth_metadata(auth_result: dict) -> tuple[str | None, str | None, str | None]:
    """Extract team_id, api_app_id, and bot user id from Slack auth.test."""
    if not auth_result.get("ok"):
        return None, None, None
    team_id = auth_result.get("team_id")
    app_id = auth_result.get("api_app_id") or auth_result.get("app_id")
    bot_user_id = auth_result.get("user_id")
    return team_id, app_id, bot_user_id


def build_slack_app_manifest(
    *,
    events_url: str,
    interactivity_url: str | None = None,
    app_name: str = DEFAULT_MANIFEST_APP_NAME,
    bot_display_name: str = DEFAULT_MANIFEST_BOT_DISPLAY_NAME,
) -> dict:
    """Build a Slack app manifest JSON object for tenant workspace setup.

    Used with Slack's "Create app → From a manifest" flow so admins skip
    manual scope, event, and App Home configuration.
    """
    return {
        "_metadata": {"major_version": 2, "minor_version": 1},
        "display_information": {
            "name": app_name,
            "description": "Chat with your LingQing agent from Slack DMs and @mentions in channels.",
            "background_color": "#1a1a2e",
        },
        "features": {
            "bot_user": {
                "display_name": bot_display_name,
                "always_online": True,
            },
            "app_home": {
                "home_tab_enabled": False,
                "messages_tab_enabled": True,
                "messages_tab_read_only_enabled": False,
            },
        },
        "oauth_config": {
            "scopes": {
                "bot": list(SLACK_BOT_SCOPES),
            },
        },
        "settings": {
            "org_deploy_enabled": False,
            "socket_mode_enabled": False,
            "event_subscriptions": {
                "request_url": events_url,
                "bot_events": list(SLACK_BOT_EVENTS),
            },
            **(
                {
                    "interactivity": {
                        "is_enabled": True,
                        "request_url": interactivity_url,
                    }
                }
                if interactivity_url
                else {}
            ),
        },
    }
