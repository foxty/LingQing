"""Ingress use-case results (no HTTP status codes)."""

from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Any

from apps.tenant_app_service.agent_ingress.slack.domain import SlackIngressAdmission
from apps.tenant_app_service.agent_ingress.slack.webhook_auth import SlackWebhookAuthFailure


class SlackEventsIngressResultKind(enum.StrEnum):
    AUTH_FAILED = "auth_failed"
    URL_VERIFICATION = "url_verification"
    ADMISSION = "admission"


@dataclass(frozen=True)
class SlackEventsIngressResult:
    """Outcome of an Events API callback after auth, admission, and side effects."""

    kind: SlackEventsIngressResultKind
    auth_failure: SlackWebhookAuthFailure | None = None
    challenge: str | None = None
    admission: SlackIngressAdmission | None = None

    @classmethod
    def auth_failed(cls, failure: SlackWebhookAuthFailure) -> SlackEventsIngressResult:
        return cls(kind=SlackEventsIngressResultKind.AUTH_FAILED, auth_failure=failure)

    @classmethod
    def url_verification(cls, challenge: str) -> SlackEventsIngressResult:
        return cls(kind=SlackEventsIngressResultKind.URL_VERIFICATION, challenge=challenge)

    @classmethod
    def from_admission(cls, admission: SlackIngressAdmission) -> SlackEventsIngressResult:
        return cls(kind=SlackEventsIngressResultKind.ADMISSION, admission=admission)


class SlackInteractivityIngressResultKind(enum.StrEnum):
    AUTH_FAILED = "auth_failed"
    INVALID_PAYLOAD = "invalid_payload"
    HANDLED = "handled"


@dataclass(frozen=True)
class SlackInteractivityIngressResult:
    """Outcome of an interactivity webhook after auth and dispatch."""

    kind: SlackInteractivityIngressResultKind
    auth_failure: SlackWebhookAuthFailure | None = None
    response_body: dict[str, Any] | None = None

    @classmethod
    def auth_failed(cls, failure: SlackWebhookAuthFailure) -> SlackInteractivityIngressResult:
        return cls(kind=SlackInteractivityIngressResultKind.AUTH_FAILED, auth_failure=failure)

    @classmethod
    def invalid_payload(cls) -> SlackInteractivityIngressResult:
        return cls(kind=SlackInteractivityIngressResultKind.INVALID_PAYLOAD)

    @classmethod
    def handled(cls, response_body: dict[str, Any]) -> SlackInteractivityIngressResult:
        return cls(kind=SlackInteractivityIngressResultKind.HANDLED, response_body=response_body)
