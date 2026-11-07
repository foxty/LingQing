"""Unit tests for Slack Events API admission (domain, no I/O)."""

import pytest

from apps.tenant_app_service.agent_ingress.slack.domain import (
    SlackIngressAdmissionOutcome,
    decide_slack_ingress_admission,
)

_DM_EVENT = {
    "type": "message",
    "channel": "D1",
    "user": "U1",
    "text": "hi",
    "ts": "1.0",
    "channel_type": "im",
    "team": "T1",
}


def _decide(**overrides):
    defaults = {
        "endpoint_enabled": True,
        "platform_config": {},
        "configured_team_id": "T1",
        "inner_event": _DM_EVENT,
        "event_id": "Ev1",
        "already_processed": False,
    }
    defaults.update(overrides)
    return decide_slack_ingress_admission(**defaults)


def test_decide_channel_chat_off_requires_notify():
    event = {
        "type": "app_mention",
        "channel": "C1",
        "user": "U1",
        "text": "<@B> hi",
        "ts": "1.0",
        "channel_type": "channel",
    }
    admission = decide_slack_ingress_admission(
        endpoint_enabled=True,
        platform_config={"channel_chat_enabled": False},
        configured_team_id="T1",
        inner_event=event,
        event_id="Ev1",
        already_processed=False,
    )
    assert admission.outcome == SlackIngressAdmissionOutcome.CHANNEL_CHAT_DISABLED


def test_decide_team_mismatch_before_duplicate():
    event = {
        "type": "app_mention",
        "channel": "C1",
        "user": "U1",
        "text": "<@B> hi",
        "ts": "1.0",
        "team": "T_WRONG",
        "channel_type": "channel",
    }
    admission = decide_slack_ingress_admission(
        endpoint_enabled=True,
        platform_config={},
        configured_team_id="T1",
        inner_event=event,
        event_id="Ev1",
        already_processed=True,
    )
    assert admission.outcome == SlackIngressAdmissionOutcome.TEAM_MISMATCH


def test_decide_accepts_dm_when_enabled():
    admission = _decide()
    assert admission.outcome == SlackIngressAdmissionOutcome.ACCEPTED
    assert admission.message_event is not None
    assert admission.message_event.source == "dm"


def test_decide_duplicate_after_accepted_path():
    admission = _decide(already_processed=True)
    assert admission.outcome == SlackIngressAdmissionOutcome.DUPLICATE


def test_decide_channel_chat_off_duplicate_skips_notify():
    event = {
        "type": "app_mention",
        "channel": "C1",
        "user": "U1",
        "text": "<@B> hi",
        "ts": "1.0",
        "team": "T1",
        "channel_type": "channel",
    }
    admission = _decide(
        inner_event=event,
        platform_config={"channel_chat_enabled": False},
        already_processed=True,
    )
    assert admission.outcome == SlackIngressAdmissionOutcome.DUPLICATE


def test_decide_integration_disabled_still_parses_message():
    admission = _decide(endpoint_enabled=False)
    assert admission.outcome == SlackIngressAdmissionOutcome.INTEGRATION_DISABLED
    assert admission.message_event is not None


def test_decide_ignored_when_unparseable():
    admission = _decide(inner_event={"type": "reaction_added", "user": "U1"})
    assert admission.outcome == SlackIngressAdmissionOutcome.IGNORED
    assert admission.ignore_reason is not None
    assert "reaction_added" in admission.ignore_reason


def test_decide_accepts_empty_app_mention_when_channel_chat_on():
    event = {
        "type": "app_mention",
        "channel": "C1",
        "user": "U1",
        "text": "",
        "ts": "1.0",
        "team": "T1",
        "channel_type": "channel",
    }
    admission = _decide(inner_event=event)
    assert admission.outcome == SlackIngressAdmissionOutcome.ACCEPTED
    assert admission.message_event is not None
    assert admission.message_event.text == ""


def test_decide_dm_still_accepted_when_channel_chat_off():
    admission = _decide(platform_config={"channel_chat_enabled": False})
    assert admission.outcome == SlackIngressAdmissionOutcome.ACCEPTED


def test_decide_integration_disabled_blocks_channel_mention_parse():
    event = {
        "type": "app_mention",
        "channel": "C1",
        "user": "U1",
        "text": "<@B>",
        "ts": "1.0",
        "team": "T1",
        "channel_type": "channel",
    }
    admission = _decide(inner_event=event, endpoint_enabled=False)
    assert admission.outcome == SlackIngressAdmissionOutcome.INTEGRATION_DISABLED
    assert admission.message_event is not None
    assert admission.message_event.source == "app_mention"

