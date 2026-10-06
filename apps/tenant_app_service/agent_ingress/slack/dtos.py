"""DTOs for Slack integration admin and webhook APIs.

Secrets are write-only: responses expose `bot_token_configured` and
`signing_secret_configured` and never the raw values.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class CreateAgentSlackIntegrationRequest(BaseModel):
    """Create a Slack bot for a specific agent."""

    bot_token: str = Field(..., min_length=1, description="Bot User OAuth Token (xoxb-...)")
    signing_secret: str = Field(..., min_length=1, description="Slack app signing secret")
    enabled: bool = False


class UpdateAgentSlackIntegrationRequest(BaseModel):
    """Update an agent Slack integration. Empty token/secret keeps the previous value."""

    bot_token: str | None = Field(default=None, description="New bot token; empty/None keeps previous")
    signing_secret: str | None = Field(default=None, description="New signing secret; empty/None keeps previous")
    enabled: bool | None = None


class SlackIntegrationResponse(BaseModel):
    """Slack integration response. Never includes raw secrets."""

    id: int
    tenant_id: int
    agent_id: int
    slack_team_id: str | None
    slack_team_name: str | None = None
    slack_app_id: str | None = None
    bot_user_id: str | None = None
    bot_token_configured: bool
    signing_secret_configured: bool
    default_agent_id: int
    enabled: bool
    endpoint_key: str
    events_url: str
    interactions_url: str


class SlackTestConnectionResponse(BaseModel):
    """Result of a Slack `auth.test` connection check."""

    ok: bool
    team_id: str | None = None
    team_name: str | None = None
    bot_user_id: str | None = None
    error: str | None = None


class SlackUrlVerificationResponse(BaseModel):
    """Slack URL verification challenge response."""

    challenge: str


class SlackWebhookAck(BaseModel):
    """Immediate ack returned to Slack for an accepted event."""

    status: str = "ok"


class BindPendingIdentityRequest(BaseModel):
    """Admin binds a pending Slack identity to a LingQing user."""

    user_id: int | None = Field(default=None, description="Internal user id to bind; None to auto-resolve by email")


class PendingIdentityResponse(BaseModel):
    """Pending Slack identity for admin review. Never includes secrets."""

    id: int
    tenant_id: int
    provider_id: int
    provider_display_name: str
    external_subject: str
    email: str | None
    display_name: str | None
    status: str
    user_id: int | None = None
    created_at: str
