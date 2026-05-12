"""Integration tests for agent-scoped Slack integration admin API."""

import json
from uuid import uuid4

import pytest

from tests.integration.conftest import make_auth_headers


async def _create_test_agent(client, token: str) -> int:
    suffix = uuid4().hex[:8]
    resp = await client.post(
        "/agents",
        headers=make_auth_headers(token),
        json={
            "name": f"Slack test agent {suffix}",
            "system_prompt": "You are a test agent.",
            "config": {},
        },
    )
    assert resp.status_code == 201
    return resp.json()["id"]


class TestAgentSlackConfigApi:
    @pytest.mark.asyncio
    async def test_create_and_get_agent_slack_integration(self, slack_test_setup):
        client = slack_test_setup["client"]
        token = slack_test_setup["tenants"]["tenant_a"]["token"]
        agent_id = await _create_test_agent(client, token)

        create_resp = await client.post(
            f"/agents/{agent_id}/integrations/slack",
            headers=make_auth_headers(token),
            json={
                "bot_token": "xoxb-agent-test",
                "signing_secret": "signing-agent-test",
                "enabled": True,
            },
        )
        assert create_resp.status_code == 201
        body = create_resp.json()
        assert body["agent_id"] == agent_id
        assert body["default_agent_id"] == agent_id
        assert body["enabled"] is True
        assert "bot_token" not in body

        get_resp = await client.get(
            f"/agents/{agent_id}/integrations/slack",
            headers=make_auth_headers(token),
        )
        assert get_resp.status_code == 200
        assert get_resp.json()["endpoint_key"] == body["endpoint_key"]

    @pytest.mark.asyncio
    async def test_two_agents_can_each_have_slack_integration(self, slack_test_setup):
        client = slack_test_setup["client"]
        token = slack_test_setup["tenants"]["tenant_a"]["token"]
        agent_a = await _create_test_agent(client, token)
        agent_b = await _create_test_agent(client, token)

        resp_a = await client.post(
            f"/agents/{agent_a}/integrations/slack",
            headers=make_auth_headers(token),
            json={
                "bot_token": "xoxb-agent-a",
                "signing_secret": "signing-agent-a",
                "enabled": False,
            },
        )
        resp_b = await client.post(
            f"/agents/{agent_b}/integrations/slack",
            headers=make_auth_headers(token),
            json={
                "bot_token": "xoxb-agent-b",
                "signing_secret": "signing-agent-b",
                "enabled": False,
            },
        )
        assert resp_a.status_code == 201
        assert resp_b.status_code == 201
        assert resp_a.json()["endpoint_key"] != resp_b.json()["endpoint_key"]

    @pytest.mark.asyncio
    async def test_create_after_manifest_provision(self, slack_test_setup):
        client = slack_test_setup["client"]
        token = slack_test_setup["tenants"]["tenant_a"]["token"]
        agent_id = await _create_test_agent(client, token)

        manifest_resp = await client.get(
            f"/agents/{agent_id}/integrations/slack/manifest",
            headers=make_auth_headers(token),
        )
        assert manifest_resp.status_code == 200
        endpoint_key = json.loads(manifest_resp.content)["settings"]["event_subscriptions"][
            "request_url"
        ].split("/ingress/")[1].split("/events")[0]

        create_resp = await client.post(
            f"/agents/{agent_id}/integrations/slack",
            headers=make_auth_headers(token),
            json={
                "bot_token": "xoxb-after-manifest",
                "signing_secret": "signing-after-manifest",
                "enabled": True,
            },
        )
        assert create_resp.status_code == 201
        assert create_resp.json()["endpoint_key"] == endpoint_key

    @pytest.mark.asyncio
    async def test_download_agent_manifest(self, slack_test_setup):
        client = slack_test_setup["client"]
        token = slack_test_setup["tenants"]["tenant_a"]["token"]
        agent_id = await _create_test_agent(client, token)
        create_resp = await client.post(
            f"/agents/{agent_id}/integrations/slack",
            headers=make_auth_headers(token),
            json={
                "bot_token": "xoxb-manifest",
                "signing_secret": "signing-manifest",
                "enabled": False,
            },
        )
        endpoint_key = create_resp.json()["endpoint_key"]

        manifest_resp = await client.get(
            f"/agents/{agent_id}/integrations/slack/manifest",
            headers=make_auth_headers(token),
        )
        assert manifest_resp.status_code == 200
        body = json.loads(manifest_resp.content)
        events_url = body["settings"]["event_subscriptions"]["request_url"]
        assert endpoint_key in events_url

    @pytest.mark.asyncio
    async def test_list_slack_endpoints_for_agents_page(self, slack_test_setup):
        client = slack_test_setup["client"]
        token = slack_test_setup["tenants"]["tenant_a"]["token"]
        agent_id = await _create_test_agent(client, token)
        await client.post(
            f"/agents/{agent_id}/integrations/slack",
            headers=make_auth_headers(token),
            json={
                "bot_token": "xoxb-list-test",
                "signing_secret": "signing-list-test",
                "enabled": False,
            },
        )

        list_resp = await client.get(
            "/integrations/slack/endpoints",
            headers=make_auth_headers(token),
        )
        assert list_resp.status_code == 200
        by_agent = {item["agent_id"]: item for item in list_resp.json()}
        assert by_agent[agent_id]["enabled"] is False
        assert -1 in by_agent

    @pytest.mark.asyncio
    async def test_unconfigured_agent_returns_204(self, slack_test_setup):
        client = slack_test_setup["client"]
        token = slack_test_setup["tenants"]["tenant_a"]["token"]
        agent_id = await _create_test_agent(client, token)
        resp = await client.get(
            f"/agents/{agent_id}/integrations/slack",
            headers=make_auth_headers(token),
        )
        assert resp.status_code == 204
