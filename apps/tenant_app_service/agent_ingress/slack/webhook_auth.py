"""Shared Slack webhook authentication (endpoint resolution + signing secret).

Used by Events API and interactivity ingress. Crypto rules live in ``domain``;
this module wires repository I/O for both webhook entry points.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from apps.shared.db.models import AgentIngressEndpoint
from apps.shared.utils.logger import get_logger
from apps.tenant_app_service.agent_ingress.slack.domain import slack_signature_failure_reason
from apps.tenant_app_service.agent_ingress.slack.repository import SlackRepository

logger = get_logger(__name__)

SlackWebhookAuthError = Literal["integration_not_found", "invalid_signature"]


@dataclass(frozen=True)
class SlackWebhookAuthFailure:
    error: SlackWebhookAuthError


async def authenticate_slack_webhook(
    repo: SlackRepository,
    *,
    endpoint_key: str,
    body_text: str,
    slack_timestamp: str,
    slack_signature: str,
) -> AgentIngressEndpoint | SlackWebhookAuthFailure:
    """Load the ingress endpoint and verify the Slack request signature."""
    endpoint = await repo.get_endpoint_by_key(endpoint_key)
    if not endpoint:
        logger.warning("Slack webhook rejected %s endpoint_found=False", endpoint_key)
        return SlackWebhookAuthFailure(error="integration_not_found")

    signing_secret = repo.decrypt_signing_secret(endpoint)
    signature_failure = slack_signature_failure_reason(
        signing_secret=signing_secret,
        timestamp=slack_timestamp,
        body=body_text,
        signature=slack_signature,
    )
    if signature_failure:
        logger.warning(
            "Slack signature verification failed %s reason=%s",
            endpoint_key,
            signature_failure,
        )
        return SlackWebhookAuthFailure(error="invalid_signature")

    return endpoint
