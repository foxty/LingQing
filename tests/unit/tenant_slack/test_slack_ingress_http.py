"""Unit tests for Slack ingress HTTP mapping (presentation)."""

import pytest

from apps.tenant_app_service.agent_ingress.slack.domain import (
    SlackIngressAdmission,
    SlackIngressAdmissionOutcome,
)
from apps.tenant_app_service.agent_ingress.slack.ingress_http import (
    slack_events_admission_http_response,
    slack_events_ingress_http_response,
)
from apps.tenant_app_service.agent_ingress.slack.ingress_results import SlackEventsIngressResult
from apps.tenant_app_service.agent_ingress.slack.ingress_router import _slack_webhook_auth_http_response
from apps.tenant_app_service.agent_ingress.slack.webhook_auth import SlackWebhookAuthFailure


def test_url_verification_http_envelope():
    result = SlackEventsIngressResult.url_verification("abc")
    status, body = slack_events_ingress_http_response(result)
    assert status == 200
    assert body == {"challenge": "abc"}


@pytest.mark.parametrize(
    ("outcome", "expected_status", "expected_body"),
    [
        (SlackIngressAdmissionOutcome.ACCEPTED, 200, {"status": "ok"}),
        (SlackIngressAdmissionOutcome.DUPLICATE, 200, {"status": "duplicate"}),
        (SlackIngressAdmissionOutcome.CHANNEL_CHAT_DISABLED, 200, {"status": "ignored"}),
        (SlackIngressAdmissionOutcome.IGNORED, 200, {"status": "ignored"}),
        (SlackIngressAdmissionOutcome.INTEGRATION_DISABLED, 200, {"status": "disabled"}),
        (SlackIngressAdmissionOutcome.TEAM_MISMATCH, 403, {"error": "team_mismatch"}),
    ],
)
def test_admission_maps_to_slack_http(outcome, expected_status, expected_body):
    admission = SlackIngressAdmission(outcome=outcome)
    status, body = slack_events_admission_http_response(admission)
    assert status == expected_status
    assert body == expected_body


def test_webhook_auth_http_response():
    status, body = _slack_webhook_auth_http_response(SlackWebhookAuthFailure(error="invalid_signature"))
    assert status == 401 and body == {"error": "invalid_signature"}
    status, body = _slack_webhook_auth_http_response(SlackWebhookAuthFailure(error="integration_not_found"))
    assert status == 404 and body == {"error": "integration_not_found"}
