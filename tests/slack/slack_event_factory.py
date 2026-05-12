"""Build synthetic Slack event payloads for integration tests.

All IDs are synthetic (test_*, uuid4 suffixes) per AGENTS.md test data rules.
"""

from __future__ import annotations

from uuid import uuid4


def make_message_event(
    *,
    user_id: str | None = None,
    channel_id: str | None = None,
    text: str = "hello from slack",
    team_id: str = "T_TEST",
    thread_ts: str | None = None,
    ts: str | None = None,
    channel_type: str = "im",
) -> dict:
    """Build a Slack message event payload (the inner `event` object)."""
    suffix = uuid4().hex[:8]
    return {
        "type": "message",
        "user": user_id or f"U_test_{suffix}",
        "channel": channel_id or f"D_test_{suffix}",
        "text": text,
        "ts": ts or f"1700000000.00{suffix[:3]}",
        "thread_ts": thread_ts,
        "channel_type": channel_type,
        "team": team_id,
    }


def make_app_mention_event(
    *,
    user_id: str | None = None,
    channel_id: str | None = None,
    text: str = "<@UBOT> hello from channel",
    team_id: str = "T_TEST",
    thread_ts: str | None = None,
    ts: str | None = None,
    channel_type: str = "channel",
) -> dict:
    """Build a Slack app_mention event payload."""
    suffix = uuid4().hex[:8]
    return {
        "type": "app_mention",
        "user": user_id or f"U_test_{suffix}",
        "channel": channel_id or f"C_test_{suffix}",
        "text": text,
        "ts": ts or f"1700000000.00{suffix[:3]}",
        "thread_ts": thread_ts,
        "channel_type": channel_type,
        "team": team_id,
    }


def make_channel_thread_reply_event(
    *,
    user_id: str | None = None,
    channel_id: str | None = None,
    text: str = "follow up in thread",
    team_id: str = "T_TEST",
    thread_ts: str = "1700000000.000100",
    ts: str | None = None,
    channel_type: str = "channel",
) -> dict:
    """Build a Slack channel thread follow-up message event."""
    suffix = uuid4().hex[:8]
    return {
        "type": "message",
        "user": user_id or f"U_test_{suffix}",
        "channel": channel_id or f"C_test_{suffix}",
        "text": text,
        "ts": ts or f"1700000000.00{suffix[:3]}",
        "thread_ts": thread_ts,
        "channel_type": channel_type,
        "team": team_id,
    }


def make_event_callback_payload(
    *,
    event: dict,
    event_id: str | None = None,
    team_id: str = "T_TEST",
) -> dict:
    """Wrap a message event in the Events API event_callback envelope."""
    suffix = uuid4().hex[:8]
    return {
        "type": "event_callback",
        "event_id": event_id or f"Ev_test_{suffix}",
        "team_id": team_id,
        "event": event,
    }


def make_url_verification_payload(challenge: str = "test-challenge-123") -> dict:
    return {"type": "url_verification", "challenge": challenge}
