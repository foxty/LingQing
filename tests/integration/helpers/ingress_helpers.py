"""Shared helpers for Slack ingress integration tests."""

from __future__ import annotations

import asyncio
import json
import time
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

from apps.shared.external_identity.identity_source_repository import IdentitySourceRepository
from apps.shared.external_identity.repository import ExternalIdentityRepository
from apps.tenant_app_service.agent_ingress.slack.source_repository import SlackIdentitySourceRepository
from tests.integration.conftest import make_auth_headers
from tests.slack.fake_slack import make_slack_signature_headers
from tests.slack.slack_event_factory import make_event_callback_payload, make_message_event


async def set_workspace_bind_policy(session_factory, *, tenant_id: int, team_id: str, bind_policy: str) -> None:
    async with session_factory() as session:
        source_repo = SlackIdentitySourceRepository(session)
        source = await source_repo.ensure_slack_workspace_source(tenant_id=tenant_id, team_id=team_id)
        await IdentitySourceRepository(session).update_bind_policy(tenant_id, source.id, bind_policy)
        await session.commit()


async def wait_until_background(assertion_coro, timeout_seconds: float = 8.0) -> None:
    """Poll until assertion passes (for asyncio background ingress tasks)."""
    deadline = time.monotonic() + timeout_seconds
    last_error = None
    while time.monotonic() < deadline:
        try:
            await assertion_coro()
            return
        except AssertionError as exc:
            last_error = exc
            await asyncio.sleep(0.2)

    if last_error is not None:
        raise last_error
    raise AssertionError("Condition was not met before timeout")


async def post_slack_dm(
    slack_test_setup,
    *,
    tenant_label: str = "tenant_a",
    slack_user: str,
    team_id: str | None = None,
    wait_seconds: float = 0.35,
) -> dict:
    """Post a signed DM event to the tenant ingress webhook."""
    client = slack_test_setup["client"]
    signing_secret = slack_test_setup["secrets"][tenant_label]
    endpoint_key = slack_test_setup["endpoint_keys"][tenant_label]
    team_id = team_id or f"T_{tenant_label.upper()}"

    event = make_message_event(user_id=slack_user, channel_id=f"D_{slack_user}", team_id=team_id)
    payload = make_event_callback_payload(event=event, event_id=f"Ev_{uuid4().hex[:8]}", team_id=team_id)
    body = json.dumps(payload)
    headers = make_slack_signature_headers(signing_secret=signing_secret, body=body)
    resp = await client.post(f"/ingress/{endpoint_key}/events", content=body, headers=headers)
    if wait_seconds:
        await asyncio.sleep(wait_seconds)
    return {"response": resp, "event": event, "payload": payload}


async def list_pending_for_user(client, token: str, slack_user: str) -> list[dict]:
    resp = await client.get("/tenants/identity/pending", headers=make_auth_headers(token))
    assert resp.status_code == 200
    return [row for row in resp.json() if row["external_subject"] == slack_user]


async def seed_pending_slack_identity(
    session_factory,
    *,
    tenant_id: int,
    team_id: str,
    slack_user: str,
    email: str,
) -> object:
    async with session_factory() as session:
        source_repo = SlackIdentitySourceRepository(session)
        identity_repo = ExternalIdentityRepository(session)
        source = await source_repo.ensure_slack_workspace_source(tenant_id=tenant_id, team_id=team_id)
        row = await identity_repo.create_identity(
            tenant_id=tenant_id,
            identity_source_id=source.id,
            external_subject=slack_user,
            user_id=None,
            email=email,
            display_name=slack_user,
            status="pending",
        )
        await session.commit()
        return row


def parse_redirect_query(location: str) -> dict[str, list[str]]:
    return parse_qs(urlparse(location).query)
