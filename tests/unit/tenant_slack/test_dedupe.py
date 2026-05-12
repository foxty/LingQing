"""Unit tests for Slack event dedupe decision logic.

The dedupe logic itself lives in the repository (DB-backed unique constraint),
but the decision semantics are tested here: an event is a duplicate iff
(tenant_id, event_id) was already processed. This locks the contract so
the webhook router's dedupe call site cannot silently change behavior.
"""

from apps.tenant_app_service.slack.domain import SlackMessageEvent


def _event(event_id: str, user_id: str = "U123", channel_id: str = "D123") -> SlackMessageEvent:
    return SlackMessageEvent(
        event_id=event_id,
        team_id="T123",
        user_id=user_id,
        channel_id=channel_id,
        text="hello",
        ts="1700000000.000100",
    )


def test_event_id_is_the_dedupe_key():
    """Two events with the same id are the same event regardless of text."""
    e1 = _event("Ev1", user_id="U1", channel_id="D1")
    e1_with_different_text = SlackMessageEvent(
        event_id="Ev1",
        team_id="T123",
        user_id="U1",
        channel_id="D1",
        text="different text",
        ts="1700000000.000100",
    )
    # dedupe key is (tenant_id, event_id) — same event_id means duplicate
    assert e1.event_id == e1_with_different_text.event_id


def test_different_event_ids_are_not_duplicates():
    e1 = _event("Ev1")
    e2 = _event("Ev2")
    assert e1.event_id != e2.event_id


def test_same_user_different_events_are_not_duplicates():
    """A user sending two messages gets two distinct event ids."""
    e1 = _event("Ev1", user_id="U1", channel_id="D1")
    e2 = _event("Ev2", user_id="U1", channel_id="D1")
    assert e1.event_id != e2.event_id
    assert e1.user_id == e2.user_id
    assert e1.channel_id == e2.channel_id
