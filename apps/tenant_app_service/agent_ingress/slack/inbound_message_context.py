"""Assemble Slack DM ingress text from user comments and forwarded/shared message payloads."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

_FORWARDED_HEADER = "[Forwarded message]"


@dataclass(frozen=True)
class SlackInboundAssembly:
    """Agent-visible input built from a Slack message event."""

    content: str
    incomplete_context: bool
    is_processable: bool


def slack_inbound_has_processable_content(event: dict[str, Any]) -> bool:
    """True when the event carries a user comment and/or extractable forwarded context."""
    if not isinstance(event, dict):
        return False
    user_comment = (event.get("text") or "").strip()
    if user_comment:
        return True
    if _shared_attachments(event):
        return True
    return False


def assemble_slack_inbound_message(
    event: dict[str, Any],
    *,
    bot_user_id: str | None = None,
) -> SlackInboundAssembly:
    """Build agent input from Slack message text plus forwarded attachment metadata."""
    if not isinstance(event, dict):
        return SlackInboundAssembly(content="", incomplete_context=False, is_processable=False)

    user_comment = (event.get("text") or "").strip()
    forward_sections: list[str] = []
    incomplete = False

    for attachment in _shared_attachments(event, bot_user_id=bot_user_id):
        section, section_incomplete = _format_forwarded_attachment(attachment)
        if section:
            forward_sections.append(section)
        incomplete = incomplete or section_incomplete

    if not user_comment and not forward_sections:
        return SlackInboundAssembly(content="", incomplete_context=False, is_processable=False)

    parts: list[str] = []
    if user_comment:
        parts.append(user_comment)
    if forward_sections:
        parts.append("\n\n".join(forward_sections))

    content = "\n\n".join(parts).strip()
    if not content:
        return SlackInboundAssembly(content="", incomplete_context=False, is_processable=False)

    return SlackInboundAssembly(
        content=content,
        incomplete_context=incomplete,
        is_processable=True,
    )


def _shared_attachments(event: dict[str, Any], *, bot_user_id: str | None = None) -> list[dict[str, Any]]:
    attachments = event.get("attachments")
    if not isinstance(attachments, list):
        return []
    shared: list[dict[str, Any]] = []
    for attachment in attachments:
        if not isinstance(attachment, dict):
            continue
        if not _is_forwarded_attachment(attachment):
            continue
        author_id = attachment.get("author_id")
        if bot_user_id and author_id == bot_user_id:
            continue
        shared.append(attachment)
    return shared


def _is_forwarded_attachment(attachment: dict[str, Any]) -> bool:
    """Distinguish Slack message shares from generic link previews."""
    if attachment.get("is_share") is True:
        return True
    if attachment.get("is_reply_unfurl") is True:
        return True
    if attachment.get("is_msg_unfurl") is True:
        if attachment.get("message_blocks") or attachment.get("channel_id") or attachment.get("author_id"):
            return True
    if attachment.get("message_blocks"):
        return True
    # Plain URL previews are not forwarded chat content.
    if attachment.get("original_url") and not attachment.get("from_url"):
        return False
    return False


def _format_forwarded_attachment(attachment: dict[str, Any]) -> tuple[str, bool]:
    body, body_incomplete = _attachment_body(attachment)
    metadata_lines = _attachment_metadata_lines(attachment)
    metadata_incomplete = _attachment_metadata_incomplete(attachment, metadata_lines)

    lines = [_FORWARDED_HEADER, *metadata_lines]
    if body:
        lines.append("---")
        lines.append(body)
    elif _attachment_has_files(attachment):
        lines.append("---")
        lines.append("(Forwarded attachment only — file/image content is not included in this version.)")
        body_incomplete = True

    section = "\n".join(lines).strip()
    return section, body_incomplete or metadata_incomplete


def _attachment_metadata_lines(attachment: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    author = attachment.get("author_name") or attachment.get("author_subname")
    author_id = attachment.get("author_id")
    if author:
        lines.append(f"Author: {author}" + (f" ({author_id})" if author_id else ""))
    elif author_id:
        lines.append(f"Author: {author_id}")

    channel_id = attachment.get("channel_id")
    if channel_id:
        lines.append(f"Source channel: {channel_id}")

    channel_team = attachment.get("channel_team")
    if channel_team:
        lines.append(f"Source workspace: {channel_team}")

    ts = attachment.get("ts")
    if ts:
        lines.append(f"Timestamp: {ts}")

    from_url = attachment.get("from_url")
    if from_url:
        lines.append(f"Permalink: {from_url}")

    footer = attachment.get("footer")
    if footer:
        lines.append(f"Context: {footer}")

    return lines


def _attachment_metadata_incomplete(attachment: dict[str, Any], metadata_lines: list[str]) -> bool:
    if not metadata_lines:
        return True
    has_author = bool(
        attachment.get("author_name") or attachment.get("author_subname") or attachment.get("author_id")
    )
    has_source = bool(attachment.get("channel_id") or attachment.get("from_url"))
    has_time = bool(attachment.get("ts"))
    return not has_author and not has_source and not has_time


def _attachment_body(attachment: dict[str, Any]) -> tuple[str, bool]:
    text = (attachment.get("text") or "").strip()
    if text:
        return text, False

    from_blocks = _text_from_message_blocks(attachment.get("message_blocks"))
    if from_blocks:
        return from_blocks, False

    fallback = (attachment.get("fallback") or "").strip()
    if fallback:
        return fallback, True

    title = (attachment.get("title") or "").strip()
    if title:
        return title, True

    return "", bool(_attachment_has_files(attachment))


def _text_from_message_blocks(message_blocks: Any) -> str:
    if not isinstance(message_blocks, list):
        return ""
    parts: list[str] = []
    for entry in message_blocks:
        if not isinstance(entry, dict):
            continue
        message = entry.get("message")
        if not isinstance(message, dict):
            continue
        blocks = message.get("blocks")
        if not isinstance(blocks, list):
            continue
        extracted = _text_from_blocks(blocks)
        if extracted:
            parts.append(extracted)
    return "\n".join(parts).strip()


def _text_from_blocks(blocks: list[Any]) -> str:
    lines: list[str] = []
    for block in blocks:
        if not isinstance(block, dict):
            continue
        block_type = block.get("type")
        if block_type == "rich_text":
            line = _rich_text_elements(block.get("elements"))
            if line:
                lines.append(line)
        elif block_type == "section":
            text_obj = block.get("text")
            if isinstance(text_obj, dict):
                text = text_obj.get("text")
                if isinstance(text, str) and text.strip():
                    lines.append(text.strip())
    return "\n".join(lines).strip()


def _rich_text_elements(elements: Any) -> str:
    if not isinstance(elements, list):
        return ""
    parts: list[str] = []
    for element in elements:
        if not isinstance(element, dict):
            continue
        element_type = element.get("type")
        if element_type == "rich_text_section":
            for item in element.get("elements") or []:
                if isinstance(item, dict) and item.get("type") == "text":
                    text = item.get("text")
                    if isinstance(text, str) and text:
                        parts.append(text)
        elif element_type == "rich_text_list":
            for sub in element.get("elements") or []:
                line = _rich_text_elements([sub])
                if line:
                    parts.append(f"• {line}")
        elif element_type == "rich_text_quote":
            quote = _rich_text_elements(element.get("elements"))
            if quote:
                parts.append(f"> {quote}")
        elif element_type == "rich_text_preformatted":
            pre = _rich_text_elements(element.get("elements"))
            if pre:
                parts.append(f"```\n{pre}\n```")
    return "".join(parts).strip()


def _attachment_has_files(attachment: dict[str, Any]) -> bool:
    files = attachment.get("files")
    return isinstance(files, list) and bool(files)