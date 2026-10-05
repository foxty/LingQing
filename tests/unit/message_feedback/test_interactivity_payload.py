"""Tests for Slack interactivity payload parsing."""

from apps.tenant_app_service.agent_ingress.slack.interactivity_service import parse_interactivity_payload


def test_parse_interactivity_payload():
    body = 'payload=%7B%22type%22%3A%22block_actions%22%7D'
    parsed = parse_interactivity_payload(body)
    assert parsed["type"] == "block_actions"
