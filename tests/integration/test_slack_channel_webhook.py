"""Integration tests for Slack channel/group chat ingress."""

import asyncio
import json
from uuid import uuid4

import pytest

from tests.slack.fake_slack import make_slack_signature_headers
from tests.slack.slack_event_factory import (
    make_app_mention_event,
    make_channel_thread_reply_event,
    make_event_callback_payload,
    make_message_event,
)


class TestSlackChannelWebhook:
    @pytest.mark.asyncio
    async def test_app_mention_in_channel_accepted(self, slack_test_setup):
        client = slack_test_setup["client"]
        tenant = slack_test_setup["tenants"]["tenant_a"]
        signing_secret = slack_test_setup["secrets"]["tenant_a"]
        fake = slack_test_setup["fake_slack"]
        slack_user = f"U_ch_{uuid4().hex[:8]}"
        channel_id = f"C_ch_{uuid4().hex[:8]}"
        fake.register_user(slack_user, email=tenant["admin"].email)

        event = make_app_mention_event(
            user_id=slack_user,
            channel_id=channel_id,
            text="<@UBOT> hello channel",
            team_id="T_TENANT_A",
            ts="1700000000.000100",
        )
        payload = make_event_callback_payload(event=event, event_id=f"Ev_{slack_user}", team_id="T_TENANT_A")
        body = json.dumps(payload)
        headers = make_slack_signature_headers(signing_secret=signing_secret, body=body)
        resp = await client.post(
            f"/ingress/{slack_test_setup['endpoint_keys']['tenant_a']}/events",
            content=body,
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

        await asyncio.sleep(0.5)
        assert fake.posted_messages, "expected bot to post thinking placeholder in channel thread"
        assert fake.posted_messages[0]["thread_ts"] == "1700000000.000100"

    @pytest.mark.asyncio
    async def test_thread_follow_up_without_mapping_is_ignored(self, slack_test_setup):
        client = slack_test_setup["client"]
        tenant = slack_test_setup["tenants"]["tenant_a"]
        signing_secret = slack_test_setup["secrets"]["tenant_a"]
        fake = slack_test_setup["fake_slack"]
        slack_user = f"U_thr_{uuid4().hex[:8]}"
        fake.register_user(slack_user, email=tenant["admin"].email)
        fake.posted_messages.clear()

        event = make_channel_thread_reply_event(
            user_id=slack_user,
            channel_id=f"C_thr_{uuid4().hex[:8]}",
            thread_ts="1700000099.000100",
            team_id="T_TENANT_A",
        )
        payload = make_event_callback_payload(event=event, event_id=f"Ev_thr_{slack_user}", team_id="T_TENANT_A")
        body = json.dumps(payload)
        headers = make_slack_signature_headers(signing_secret=signing_secret, body=body)
        resp = await client.post(
            f"/ingress/{slack_test_setup['endpoint_keys']['tenant_a']}/events",
            content=body,
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
        await asyncio.sleep(0.5)
        assert not fake.posted_messages
        assert not fake.updated_messages

    @pytest.mark.asyncio
    async def test_top_level_channel_message_is_ignored(self, slack_test_setup):
        client = slack_test_setup["client"]
        tenant = slack_test_setup["tenants"]["tenant_a"]
        signing_secret = slack_test_setup["secrets"]["tenant_a"]

        event = make_message_event(
            channel_id=f"C_top_{uuid4().hex[:8]}",
            channel_type="channel",
            team_id="T_TENANT_A",
        )
        payload = make_event_callback_payload(event=event, event_id=f"Ev_top_{uuid4().hex[:8]}", team_id="T_TENANT_A")
        body = json.dumps(payload)
        headers = make_slack_signature_headers(signing_secret=signing_secret, body=body)
        resp = await client.post(
            f"/ingress/{slack_test_setup['endpoint_keys']['tenant_a']}/events",
            content=body,
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ignored"

    @pytest.mark.asyncio
    async def test_thread_follow_up_continues_existing_channel_thread(self, slack_test_setup):
        client = slack_test_setup["client"]
        tenant = slack_test_setup["tenants"]["tenant_a"]
        signing_secret = slack_test_setup["secrets"]["tenant_a"]
        fake = slack_test_setup["fake_slack"]
        slack_user = f"U_cont_{uuid4().hex[:8]}"
        channel_id = f"C_cont_{uuid4().hex[:8]}"
        thread_root = "1700000000.000500"
        fake.register_user(slack_user, email=tenant["admin"].email)

        mention = make_app_mention_event(
            user_id=slack_user,
            channel_id=channel_id,
            text="<@UBOT> start thread",
            team_id="T_TENANT_A",
            ts=thread_root,
        )
        mention_body = json.dumps(
            make_event_callback_payload(event=mention, event_id=f"Ev_cont_m_{slack_user}", team_id="T_TENANT_A")
        )
        headers = make_slack_signature_headers(signing_secret=signing_secret, body=mention_body)
        url = f"/ingress/{slack_test_setup['endpoint_keys']['tenant_a']}/events"
        resp1 = await client.post(url, content=mention_body, headers=headers)
        assert resp1.status_code == 200
        await asyncio.sleep(0.5)
        fake.posted_messages.clear()
        fake.updated_messages.clear()

        follow_up = make_channel_thread_reply_event(
            user_id=slack_user,
            channel_id=channel_id,
            text="continue please",
            thread_ts=thread_root,
            team_id="T_TENANT_A",
        )
        follow_body = json.dumps(
            make_event_callback_payload(
                event=follow_up,
                event_id=f"Ev_cont_f_{slack_user}",
                team_id="T_TENANT_A",
            )
        )
        headers2 = make_slack_signature_headers(signing_secret=signing_secret, body=follow_body)
        resp2 = await client.post(url, content=follow_body, headers=headers2)
        assert resp2.status_code == 200
        assert resp2.json()["status"] == "ok"

        await asyncio.sleep(0.5)
        assert fake.posted_messages or fake.updated_messages

    @pytest.mark.asyncio
    async def test_unbound_user_app_mention_posts_in_thread_error(self, slack_test_setup):
        client = slack_test_setup["client"]
        tenant = slack_test_setup["tenants"]["tenant_a"]
        signing_secret = slack_test_setup["secrets"]["tenant_a"]
        fake = slack_test_setup["fake_slack"]
        slack_user = f"U_denied_{uuid4().hex[:8]}"
        external_domain = tenant["external_domain"]
        fake.register_user(slack_user, email=f"unknown_{uuid4().hex[:8]}@{external_domain}")
        fake.posted_messages.clear()

        event = make_app_mention_event(
            user_id=slack_user,
            channel_id=f"C_denied_{uuid4().hex[:8]}",
            team_id="T_TENANT_A",
            ts="1700000000.000900",
        )
        payload = make_event_callback_payload(event=event, event_id=f"Ev_denied_{slack_user}", team_id="T_TENANT_A")
        body = json.dumps(payload)
        headers = make_slack_signature_headers(signing_secret=signing_secret, body=body)
        resp = await client.post(
            f"/ingress/{slack_test_setup['endpoint_keys']['tenant_a']}/events",
            content=body,
            headers=headers,
        )
        assert resp.status_code == 200
        await asyncio.sleep(0.5)
        assert any("No LingQing account" in m["text"] for m in fake.posted_messages)
