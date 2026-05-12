"""Unit tests for Slack event classification (pure, no DB)."""

from apps.tenant_app_service.slack.domain import (
    SlackMessageEvent,
    is_processable_message_event,
    parse_app_mention_event,
    parse_message_event,
    parse_thread_reply_event,
    slack_mapping_thread_ts,
    slack_reply_thread_ts,
    slack_thread_root_ts,
    strip_bot_mention,
)


def _dm_event(**overrides) -> dict:
    base = {
        "type": "message",
        "channel": "D123",
        "user": "U123",
        "text": "hello",
        "ts": "1700000000.000100",
        "channel_type": "im",
    }
    base.update(overrides)
    return base


def test_accepts_dm_message_with_text():
    assert is_processable_message_event(_dm_event()) is True


def test_ignores_bot_message_via_bot_id():
    assert is_processable_message_event(_dm_event(bot_id="B123")) is False


def test_ignores_bot_message_via_subtype():
    assert is_processable_message_event(_dm_event(subtype="bot_message")) is False


def test_ignores_message_changed():
    assert is_processable_message_event(_dm_event(subtype="message_changed")) is False


def test_ignores_message_deleted():
    assert is_processable_message_event(_dm_event(subtype="message_deleted")) is False


def test_ignores_empty_text():
    assert is_processable_message_event(_dm_event(text="   ")) is False


def test_ignores_file_only_message():
    assert is_processable_message_event(_dm_event(text="")) is False


def test_parse_message_event_returns_dm():
    parsed = parse_message_event(_dm_event(), event_id="Ev123")
    assert parsed is not None
    assert parsed.user_id == "U123"
    assert parsed.channel_id == "D123"
    assert parsed.text == "hello"
    assert parsed.event_id == "Ev123"
    assert parsed.channel_type == "im"


def test_parse_message_event_rejects_non_dm_channel():
    parsed = parse_message_event(_dm_event(channel_type="channel"), event_id="Ev123")
    assert parsed is None


def test_parse_message_event_rejects_bot_message():
    parsed = parse_message_event(_dm_event(bot_id="B1"), event_id="Ev123")
    assert parsed is None


def test_parse_message_event_rejects_missing_user():
    parsed = parse_message_event(_dm_event(user=""), event_id="Ev123")
    assert parsed is None


def test_parse_message_event_falls_back_to_ts_for_event_id():
    parsed = parse_message_event(_dm_event(), event_id=None)
    assert parsed is not None
    assert parsed.event_id == "1700000000.000100"


def test_slack_reply_thread_ts_flat_for_top_level_dm():
    assert (
        slack_reply_thread_ts(channel_type="im", thread_ts=None, message_ts="1700000000.000100")
        is None
    )


def test_slack_reply_thread_ts_follows_user_thread_in_dm():
    assert (
        slack_reply_thread_ts(
            channel_type="im", thread_ts="1700000000.000050", message_ts="1700000000.000100"
        )
        == "1700000000.000050"
    )


def test_slack_reply_thread_ts_threads_in_shared_channel():
    assert (
        slack_reply_thread_ts(channel_type="channel", thread_ts=None, message_ts="1700000000.000100")
        == "1700000000.000100"
    )


def test_slack_thread_root_ts_prefers_thread_ts():
    assert slack_thread_root_ts(thread_ts="1.0", message_ts="2.0") == "1.0"
    assert slack_thread_root_ts(thread_ts=None, message_ts="2.0") == "2.0"


def _channel_event(**overrides) -> dict:
    base = {
        "type": "message",
        "channel": "C123",
        "user": "U123",
        "text": "hello channel",
        "ts": "1700000000.000200",
        "channel_type": "channel",
        "thread_ts": "1700000000.000100",
    }
    base.update(overrides)
    return base


def test_parse_app_mention_event_returns_channel_mention():
    event = {
        "type": "app_mention",
        "channel": "C123",
        "user": "U123",
        "text": "<@UBOT> summarize this",
        "ts": "1700000000.000100",
        "channel_type": "channel",
    }
    parsed = parse_app_mention_event(event, event_id="EvM1")
    assert parsed is not None
    assert parsed.source == "app_mention"
    assert parsed.channel_type == "channel"
    assert parsed.text == "<@UBOT> summarize this"


def test_parse_thread_reply_event_accepts_channel_follow_up():
    parsed = parse_thread_reply_event(_channel_event(), event_id="EvT1")
    assert parsed is not None
    assert parsed.source == "thread_reply"
    assert parsed.thread_ts == "1700000000.000100"


def test_parse_thread_reply_event_rejects_top_level_channel_message():
    parsed = parse_thread_reply_event(
        _channel_event(thread_ts=None),
        event_id="EvT2",
    )
    assert parsed is None


def test_parse_thread_reply_event_rejects_dm_thread():
    parsed = parse_thread_reply_event(
        _channel_event(channel_type="im", thread_ts="1700000000.000100"),
        event_id="EvT3",
    )
    assert parsed is None


def test_strip_bot_mention_removes_leading_markup():
    assert strip_bot_mention("<@UBOT> hello") == "hello"
    assert strip_bot_mention("<@UBOT>hello") == "hello"
    assert strip_bot_mention("hello", bot_user_id="UBOT") == "hello"


def test_slack_mapping_thread_ts_empty_for_dm():
    event = SlackMessageEvent(
        event_id="Ev1",
        team_id="T1",
        user_id="U1",
        channel_id="D1",
        text="hi",
        ts="1.0",
        channel_type="im",
    )
    assert slack_mapping_thread_ts(event) == ""


def test_slack_mapping_thread_ts_uses_root_for_channel():
    event = SlackMessageEvent(
        event_id="Ev1",
        team_id="T1",
        user_id="U1",
        channel_id="C1",
        text="hi",
        ts="2.0",
        thread_ts="1.0",
        channel_type="channel",
        source="thread_reply",
    )
    assert slack_mapping_thread_ts(event) == "1.0"
