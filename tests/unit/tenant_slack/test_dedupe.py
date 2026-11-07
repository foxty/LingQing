"""Unit tests for Slack ingress message dedupe identity (domain contract).

Persistence uses ``(tenant_id, slack_channel_id, message_ts)`` in
``slack_processed_events``; see repository ``is_message_already_processed``.
"""

from apps.tenant_app_service.agent_ingress.slack.domain import SlackMessageEvent


def _event(event_id: str, user_id: str = "U123", channel_id: str = "D123", ts: str = "1700000000.000100") -> SlackMessageEvent:
    return SlackMessageEvent(
        event_id=event_id,
        team_id="T123",
        user_id=user_id,
        channel_id=channel_id,
        text="hello",
        ts=ts,
    )


def test_same_channel_and_ts_same_delivery_different_envelope_ids():
    """app_mention + message mirror share channel id and message ts."""
    e1 = _event("Ev_outer_1", channel_id="C1", ts="1700000000.000200")
    e2 = SlackMessageEvent(
        event_id="Ev_outer_2",
        team_id="T123",
        user_id="U1",
        channel_id="C1",
        text="<@B>",
        ts="1700000000.000200",
        source="app_mention",
    )
    assert e1.channel_id == e2.channel_id
    assert e1.ts == e2.ts
    assert e1.event_id != e2.event_id


def test_different_message_ts_are_distinct_deliveries():
    e1 = _event("Ev1", channel_id="C1", ts="1700000000.000100")
    e2 = _event("Ev2", channel_id="C1", ts="1700000000.000101")
    assert e1.ts != e2.ts
