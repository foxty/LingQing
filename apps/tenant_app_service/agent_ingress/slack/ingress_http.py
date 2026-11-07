"""Presentation helpers: Slack ingress results → HTTP status and JSON body."""

from __future__ import annotations

from apps.tenant_app_service.agent_ingress.slack.domain import (
    SlackIngressAdmission,
    SlackIngressAdmissionOutcome,
)
from apps.tenant_app_service.agent_ingress.slack.ingress_results import (
    SlackEventsIngressResult,
    SlackEventsIngressResultKind,
)


def slack_events_ingress_http_response(result: SlackEventsIngressResult) -> tuple[int, dict]:
    """Map events ingress result to HTTP (``auth_failed`` is handled in the router)."""
    if result.kind == SlackEventsIngressResultKind.URL_VERIFICATION:
        return 200, {"challenge": result.challenge or ""}
    if result.kind == SlackEventsIngressResultKind.ADMISSION and result.admission is not None:
        return slack_events_admission_http_response(result.admission)
    return 200, {"status": "ignored"}


def slack_events_admission_http_response(admission: SlackIngressAdmission) -> tuple[int, dict]:
    """Map ingress admission to Slack Events API ack JSON."""
    outcome = admission.outcome
    if outcome == SlackIngressAdmissionOutcome.TEAM_MISMATCH:
        return 403, {"error": "team_mismatch"}
    if outcome == SlackIngressAdmissionOutcome.INTEGRATION_DISABLED:
        return 200, {"status": "disabled"}
    if outcome == SlackIngressAdmissionOutcome.DUPLICATE:
        return 200, {"status": "duplicate"}
    if outcome in (
        SlackIngressAdmissionOutcome.CHANNEL_CHAT_DISABLED,
        SlackIngressAdmissionOutcome.IGNORED,
    ):
        return 200, {"status": "ignored"}
    if outcome == SlackIngressAdmissionOutcome.ACCEPTED:
        return 200, {"status": "ok"}
    return 200, {"status": "ignored"}
