"""Integration tests for the Slack admin config API (agent-scoped)."""

import json
from uuid import uuid4

import pytest

from apps.tenant_app_service.agent_catalog.domain import SYSTEM_AGENT_ONE_ID
from tests.integration.conftest import make_auth_headers

AGENT_SLACK = f"/agents/{SYSTEM_AGENT_ONE_ID}/integrations/slack"


async def _create_test_agent(client, token: str) -> int:
    suffix = uuid4().hex[:8]
    resp = await client.post(
        "/agents",
        headers=make_auth_headers(token),
        json={
            "name": f"Slack config test agent {suffix}",
            "system_prompt": "You are a test agent.",
            "config": {},
        },
    )
    assert resp.status_code == 201
    return resp.json()["id"]


async def _create_agent_slack(client, token: str, agent_id: int, *, enabled: bool = True) -> dict:
    suffix = uuid4().hex[:8]
    resp = await client.post(
        f"/agents/{agent_id}/integrations/slack",
        headers=make_auth_headers(token),
        json={
            "bot_token": f"xoxb-config-{suffix}",
            "signing_secret": f"signing-config-{suffix}",
            "enabled": enabled,
        },
    )
    assert resp.status_code == 201
    return resp.json()


class TestSlackConfigApi:
    @pytest.mark.asyncio
    async def test_get_integration_admin_allowed(self, slack_test_setup):
        client = slack_test_setup["client"]
        token = slack_test_setup["tenants"]["tenant_a"]["token"]
        agent_id = await _create_test_agent(client, token)
        await _create_agent_slack(client, token, agent_id)

        resp = await client.get(
            f"/agents/{agent_id}/integrations/slack",
            headers=make_auth_headers(token),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["enabled"] is True
        assert body["bot_token_configured"] is True
        assert body["signing_secret_configured"] is True
        assert body["slack_team_id"] == "T_FAKE"
        assert body["slack_app_id"]
        assert body["bot_user_id"]
        assert "bot_token" not in body
        assert "signing_secret" not in body

    @pytest.mark.asyncio
    async def test_get_integration_unauthenticated_denied(self, slack_test_setup):
        client = slack_test_setup["client"]
        resp = await client.get("/agents/1/integrations/slack")
        assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_tenant_a_cannot_read_tenant_b_config(self, slack_test_setup):
        client = slack_test_setup["client"]
        token_a = slack_test_setup["tenants"]["tenant_a"]["token"]
        token_b = slack_test_setup["tenants"]["tenant_b"]["token"]
        agent_id = await _create_test_agent(client, token_b)
        await _create_agent_slack(client, token_b, agent_id)

        resp = await client.get(
            f"/agents/{agent_id}/integrations/slack",
            headers=make_auth_headers(token_a),
        )
        assert resp.status_code in (403, 404)

    @pytest.mark.asyncio
    async def test_test_connection_returns_team_info(self, slack_test_setup):
        client = slack_test_setup["client"]
        token = slack_test_setup["tenants"]["tenant_a"]["token"]
        agent_id = await _create_test_agent(client, token)
        await _create_agent_slack(client, token, agent_id)

        resp = await client.post(
            f"/agents/{agent_id}/integrations/slack/test",
            headers=make_auth_headers(token),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["team_id"] == "T_FAKE"

    @pytest.mark.asyncio
    async def test_disable_integration(self, slack_test_setup):
        client = slack_test_setup["client"]
        token = slack_test_setup["tenants"]["tenant_a"]["token"]
        agent_id = await _create_test_agent(client, token)
        await _create_agent_slack(client, token, agent_id)

        resp = await client.post(
            f"/agents/{agent_id}/integrations/slack/disable",
            headers=make_auth_headers(token),
        )
        assert resp.status_code == 200
        assert resp.json()["enabled"] is False

    @pytest.mark.asyncio
    async def test_prepare_provisions_endpoint(self, slack_test_setup):
        client = slack_test_setup["client"]
        token = slack_test_setup["tenants"]["tenant_a"]["token"]
        agent_id = await _create_test_agent(client, token)

        resp = await client.post(
            f"/agents/{agent_id}/integrations/slack/prepare",
            headers=make_auth_headers(token),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["agent_id"] == agent_id
        assert body["events_url"]
        assert body["bot_token_configured"] is False

    @pytest.mark.asyncio
    async def test_download_manifest_without_integration_provisions_endpoint(self, slack_test_setup):
        client = slack_test_setup["client"]
        token = slack_test_setup["tenants"]["tenant_a"]["token"]
        agent_id = await _create_test_agent(client, token)

        manifest_resp = await client.get(
            f"/agents/{agent_id}/integrations/slack/manifest",
            headers=make_auth_headers(token),
        )
        assert manifest_resp.status_code == 200
        body = json.loads(manifest_resp.content)
        events_url = body["settings"]["event_subscriptions"]["request_url"]
        assert "/ingress/" in events_url

        get_resp = await client.get(
            f"/agents/{agent_id}/integrations/slack",
            headers=make_auth_headers(token),
        )
        assert get_resp.status_code == 200
        assert get_resp.json()["events_url"] == events_url
        assert get_resp.json()["bot_token_configured"] is False

    @pytest.mark.asyncio
    async def test_download_manifest_includes_ingress_events_url(self, slack_test_setup):
        client = slack_test_setup["client"]
        token = slack_test_setup["tenants"]["tenant_a"]["token"]
        agent_id = await _create_test_agent(client, token)
        created = await _create_agent_slack(client, token, agent_id)

        resp = await client.get(
            f"/agents/{agent_id}/integrations/slack/manifest",
            headers=make_auth_headers(token),
        )
        assert resp.status_code == 200
        assert "attachment" in resp.headers.get("content-disposition", "")
        body = resp.json()
        events_url = body["settings"]["event_subscriptions"]["request_url"]
        assert "/ingress/" in events_url
        assert events_url.endswith("/events")
        assert created["endpoint_key"] in events_url
        assert "message.im" in body["settings"]["event_subscriptions"]["bot_events"]

    @pytest.mark.asyncio
    async def test_get_integration_not_configured_returns_204(self, slack_test_setup):
        client = slack_test_setup["client"]
        token = slack_test_setup["tenants"]["tenant_a"]["token"]
        agent_id = await _create_test_agent(client, token)

        resp = await client.get(
            f"/agents/{agent_id}/integrations/slack",
            headers=make_auth_headers(token),
        )
        assert resp.status_code == 204
        assert resp.content == b""

    @pytest.mark.asyncio
    async def test_builtin_agent_slack_integration(self, slack_test_setup):
        client = slack_test_setup["client"]
        token = slack_test_setup["tenants"]["tenant_a"]["token"]
        resp = await client.get(AGENT_SLACK, headers=make_auth_headers(token))
        assert resp.status_code == 200
        assert resp.json()["agent_id"] == SYSTEM_AGENT_ONE_ID
