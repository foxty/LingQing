"""Integration tests for the Slack Events API webhook (ingress security).

Verifies URL verification challenge, signature verification, timestamp
expiry, team_id mismatch, and event dedupe. Uses the fake Slack client
for any outbound calls; the webhook itself is verified by signing secret.
"""

import asyncio
import json
import time
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from apps.tenant_app_service.agent_catalog.domain import SYSTEM_AGENT_ONE_ID
from sqlalchemy import func, select

from tests.slack.fake_slack import make_slack_signature_headers
from tests.slack.slack_event_factory import (
    make_event_callback_payload,
    make_message_event,
    make_url_verification_payload,
)


async def _wait_until(assertion_coro, timeout_seconds: float = 8.0) -> None:
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


class TestSlackWebhook:
    @pytest.mark.asyncio
    async def test_url_verification_returns_challenge(self, slack_test_setup):
        client = slack_test_setup["client"]
        signing_secret = slack_test_setup["secrets"]["tenant_a"]
        payload = make_url_verification_payload("my-challenge-abc")
        body = json.dumps(payload)
        headers = make_slack_signature_headers(signing_secret=signing_secret, body=body)
        resp = await client.post(
            f"/ingress/{slack_test_setup['endpoint_keys']['tenant_a']}/events",
            content=body,
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["challenge"] == "my-challenge-abc"

    @pytest.mark.asyncio
    async def test_invalid_signature_returns_401(self, slack_test_setup):
        client = slack_test_setup["client"]
        tenant_id = slack_test_setup["tenants"]["tenant_a"]["tenant"].id
        event = make_message_event(user_id="U_test_1", channel_id="D_test_1")
        payload = make_event_callback_payload(event=event, event_id="Ev_test_1")
        body = json.dumps(payload)
        resp = await client.post(
            f"/ingress/{slack_test_setup['endpoint_keys']['tenant_a']}/events",
            content=body,
            headers={
                "X-Slack-Signature": "v0=invalid",
                "X-Slack-Request-Timestamp": "1700000000",
                "Content-Type": "application/json",
            },
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_valid_signature_accepts_event(self, slack_test_setup):
        """A validly signed DM message is accepted (200) and processed in background."""
        client = slack_test_setup["client"]
        tenant = slack_test_setup["tenants"]["tenant_a"]
        signing_secret = slack_test_setup["secrets"]["tenant_a"]
        fake = slack_test_setup["fake_slack"]
        fake.register_user("U_test_valid", email=tenant["admin"].email)

        event = make_message_event(user_id="U_test_valid", channel_id="D_test_valid", text="hi", team_id="T_TENANT_A")
        payload = make_event_callback_payload(event=event, event_id="Ev_test_valid", team_id="T_TENANT_A")
        body = json.dumps(payload)
        headers = make_slack_signature_headers(signing_secret=signing_secret, body=body)
        resp = await client.post(
            f"/ingress/{slack_test_setup['endpoint_keys']['tenant_a']}/events",
            content=body,
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    @pytest.mark.asyncio
    async def test_disabled_integration_notifies_slack_user(self, slack_test_setup):
        client = slack_test_setup["client"]
        token = slack_test_setup["tenants"]["tenant_a"]["token"]
        signing_secret = slack_test_setup["secrets"]["tenant_a"]
        fake = slack_test_setup["fake_slack"]
        endpoint_key = slack_test_setup["endpoint_keys"]["tenant_a"]

        disable_resp = await client.post(
            f"/agents/{SYSTEM_AGENT_ONE_ID}/integrations/slack/disable",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert disable_resp.status_code == 200
        assert disable_resp.json()["enabled"] is False

        fake.posted_messages.clear()
        event = make_message_event(
            user_id="U_disabled",
            channel_id="D_disabled",
            text="hello",
            team_id="T_TENANT_A",
        )
        payload = make_event_callback_payload(event=event, event_id="Ev_disabled", team_id="T_TENANT_A")
        body = json.dumps(payload)
        headers = make_slack_signature_headers(signing_secret=signing_secret, body=body)
        resp = await client.post(
            f"/ingress/{endpoint_key}/events",
            content=body,
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "disabled"

        async def _assert_disabled_notification() -> None:
            assert fake.posted_messages
            assert "disabled" in fake.posted_messages[0]["text"].lower()

        await _wait_until(_assert_disabled_notification)

    @pytest.mark.asyncio
    async def test_team_id_mismatch_returns_403(self, slack_test_setup):
        """An event whose team_id does not match the configured workspace is rejected."""
        client = slack_test_setup["client"]
        tenant = slack_test_setup["tenants"]["tenant_a"]
        signing_secret = slack_test_setup["secrets"]["tenant_a"]
        fake = slack_test_setup["fake_slack"]
        fake.register_user("U_test_mismatch", email=tenant["admin"].email)

        event = make_message_event(user_id="U_test_mismatch", channel_id="D_test_mismatch", team_id="T_OTHER")
        payload = make_event_callback_payload(event=event, event_id="Ev_test_mismatch", team_id="T_OTHER")
        body = json.dumps(payload)
        headers = make_slack_signature_headers(signing_secret=signing_secret, body=body)
        resp = await client.post(
            f"/ingress/{slack_test_setup['endpoint_keys']['tenant_a']}/events",
            content=body,
            headers=headers,
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_duplicate_event_acked_without_reprocessing(self, slack_test_setup):
        """A duplicate event_id is acked with status=duplicate."""
        client = slack_test_setup["client"]
        tenant = slack_test_setup["tenants"]["tenant_a"]
        signing_secret = slack_test_setup["secrets"]["tenant_a"]
        fake = slack_test_setup["fake_slack"]
        fake.register_user("U_test_dup", email=tenant["admin"].email)

        event = make_message_event(user_id="U_test_dup", channel_id="D_test_dup", team_id="T_TENANT_A")
        payload = make_event_callback_payload(event=event, event_id="Ev_dup_1", team_id="T_TENANT_A")
        body = json.dumps(payload)
        headers = make_slack_signature_headers(signing_secret=signing_secret, body=body)
        url = f"/ingress/{slack_test_setup['endpoint_keys']['tenant_a']}/events"

        resp1 = await client.post(url, content=body, headers=headers)
        assert resp1.status_code == 200
        assert resp1.json()["status"] == "ok"

        # Same event_id again -> duplicate
        resp2 = await client.post(url, content=body, headers=headers)
        assert resp2.status_code == 200
        assert resp2.json()["status"] == "duplicate"

    @pytest.mark.asyncio
    async def test_unknown_endpoint_key_returns_404(self, slack_test_setup):
        """Unknown endpoint_key cannot resolve an ingress endpoint."""
        client = slack_test_setup["client"]
        payload = make_event_callback_payload(event=make_message_event(), event_id="Ev_noendpoint")
        body = json.dumps(payload)
        resp = await client.post(
            "/ingress/unknown-endpoint-key/events",
            content=body,
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_legacy_tenant_webhook_removed(self, slack_test_setup):
        client = slack_test_setup["client"]
        tenant_id = slack_test_setup["tenants"]["tenant_a"]["tenant"].id
        resp = await client.post(
            f"/integrations/slack/events?tenant={tenant_id}",
            content="{}",
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_thread_link_lookup_ignores_stale_agent_id(self, slack_test_setup, pg_async_db_session):
        """Migrated links with legacy agent_id still resolve via endpoint conversation key."""
        from uuid import uuid4

        from apps.tenant_app_service.slack.repository import SlackRepository

        tenant_id = slack_test_setup["tenants"]["tenant_a"]["tenant"].id
        channel_id = f"D_{uuid4().hex[:8]}"
        chat_thread_id = f"thread_{uuid4().hex[:8]}"

        repo = SlackRepository(pg_async_db_session)
        endpoint = await repo.get_endpoint(tenant_id)
        assert endpoint is not None

        await repo.create_thread_link(
            tenant_id=tenant_id,
            endpoint_id=endpoint.id,
            agent_id=-1,
            external_user_id="U_legacy",
            external_channel_id=channel_id,
            chat_thread_id=chat_thread_id,
            external_thread_key="",
        )
        await pg_async_db_session.commit()

        found = await repo.get_thread_link(
            tenant_id,
            channel_id,
            "",
            endpoint_id=endpoint.id,
        )
        assert found is not None
        assert found.chat_thread_id == chat_thread_id
        assert found.agent_id == -1

    @pytest.mark.asyncio
    async def test_create_thread_link_is_idempotent(self, slack_test_setup, pg_async_db_session):
        """Duplicate create calls for the same endpoint conversation key return one row."""
        from apps.shared.db.models import IngressThreadLink
        from apps.tenant_app_service.slack.repository import SlackRepository

        tenant_id = slack_test_setup["tenants"]["tenant_a"]["tenant"].id
        channel_id = f"D_{uuid4().hex[:8]}"
        first_thread_id = f"thread_{uuid4().hex[:8]}"
        second_thread_id = f"thread_{uuid4().hex[:8]}"

        repo = SlackRepository(pg_async_db_session)
        endpoint = await repo.get_endpoint(tenant_id)
        assert endpoint is not None

        first = await repo.create_thread_link(
            tenant_id=tenant_id,
            endpoint_id=endpoint.id,
            agent_id=-1,
            external_user_id="U_legacy",
            external_channel_id=channel_id,
            chat_thread_id=first_thread_id,
            external_thread_key="",
        )
        second = await repo.create_thread_link(
            tenant_id=tenant_id,
            endpoint_id=endpoint.id,
            agent_id=endpoint.agent_id,
            external_user_id="U_legacy",
            external_channel_id=channel_id,
            chat_thread_id=second_thread_id,
            external_thread_key="",
        )
        await pg_async_db_session.commit()

        assert second.id == first.id
        assert second.chat_thread_id == first_thread_id

        count = await pg_async_db_session.scalar(
            select(func.count())
            .select_from(IngressThreadLink)
            .where(
                IngressThreadLink.endpoint_id == endpoint.id,
                IngressThreadLink.external_channel_id == channel_id,
                IngressThreadLink.external_thread_key == "",
            )
        )
        assert count == 1

    @pytest.mark.asyncio
    async def test_dm_rebinds_when_migrated_link_points_at_wrong_agent(
        self, slack_test_setup, monkeypatch
    ):
        """Regression: stale ingress links must rebind to endpoint agent, not reuse legacy threads."""
        from apps.shared.db.models import AgentIngressEndpoint, ChatThread, IngressThreadLink
        from apps.tenant_app_service.slack.repository import SlackRepository

        client = slack_test_setup["client"]
        tenant = slack_test_setup["tenants"]["tenant_a"]
        signing_secret = slack_test_setup["secrets"]["tenant_a"]
        fake = slack_test_setup["fake_slack"]
        session_factory = slack_test_setup["session_factory"]
        tenant_id = tenant["tenant"].id
        user_id = tenant["admin"].id
        slack_user = f"U_migrated_{uuid4().hex[:8]}"
        channel_id = f"D_{uuid4().hex[:8]}"
        migrated_thread_id = f"{tenant_id}_{user_id}_-1_{uuid4().hex[:8]}"
        endpoint_id: int
        fake.register_user(slack_user, email=tenant["admin"].email)
        fake.posted_messages.clear()

        async with session_factory() as seed_session:
            repo = SlackRepository(seed_session)
            endpoint = await repo.get_endpoint(tenant_id)
            assert endpoint is not None
            endpoint_id = endpoint.id
            endpoint.agent_id = 1
            await seed_session.flush()

            seed_session.add(
                ChatThread(
                    id=migrated_thread_id,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    agent_id=-1,
                    title=f"Slack DM with {slack_user}",
                    message_count=0,
                )
            )
            await seed_session.flush()
            await repo.create_thread_link(
                tenant_id=tenant_id,
                endpoint_id=endpoint.id,
                agent_id=-1,
                external_user_id=slack_user,
                external_channel_id=channel_id,
                chat_thread_id=migrated_thread_id,
                external_thread_key="",
            )
            await seed_session.commit()

        captured: dict[str, object] = {}

        async def fake_chat(self, request, **kwargs):
            captured["thread_id"] = request.thread_id
            captured["agent_id"] = request.agent_id
            return MagicMock(response=MagicMock(content="reused thread ok"))

        monkeypatch.setattr(
            "apps.tenant_app_service.slack.ingress_service.ChatService.chat",
            fake_chat,
        )

        event = make_message_event(
            user_id=slack_user,
            channel_id=channel_id,
            text="follow-up dm",
            team_id="T_TENANT_A",
        )
        payload = make_event_callback_payload(event=event, event_id=f"Ev_{uuid4().hex[:8]}", team_id="T_TENANT_A")
        body = json.dumps(payload)
        headers = make_slack_signature_headers(signing_secret=signing_secret, body=body)
        resp = await client.post(
            f"/ingress/{slack_test_setup['endpoint_keys']['tenant_a']}/events",
            content=body,
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

        async def _assert_rebound() -> None:
            assert "thread_id" in captured
            assert captured["thread_id"] != migrated_thread_id
            assert captured["agent_id"] == 1
            assert fake.posted_messages, "expected bot reply after rebinding migrated thread link"

        await _wait_until(_assert_rebound)

        async with session_factory() as verify_session:
            linked_thread_id = await verify_session.scalar(
                select(IngressThreadLink.chat_thread_id).where(
                    IngressThreadLink.endpoint_id == endpoint_id,
                    IngressThreadLink.external_channel_id == channel_id,
                    IngressThreadLink.external_thread_key == "",
                )
            )
            endpoint_agent_id = await verify_session.scalar(
                select(AgentIngressEndpoint.agent_id).where(AgentIngressEndpoint.id == endpoint_id)
            )

        assert linked_thread_id == captured["thread_id"]
        assert endpoint_agent_id == 1

    @pytest.mark.asyncio
    async def test_delete_thread_removes_ingress_thread_link(self, slack_test_setup):
        """Deleting a chat thread from the UI should drop dangling Slack ingress links."""
        from uuid import uuid4

        from sqlalchemy import func, select

        from apps.shared.db.models import ChatThread, IngressThreadLink
        from apps.tenant_app_service.chat.service import ChatService
        from apps.tenant_app_service.slack.repository import SlackRepository

        tenant = slack_test_setup["tenants"]["tenant_a"]
        session_factory = slack_test_setup["session_factory"]
        tenant_id = tenant["tenant"].id
        user_id = tenant["admin"].id
        channel_id = f"D_{uuid4().hex[:8]}"
        chat_thread_id = f"2_{tenant_id}_{user_id}_1_{uuid4().hex[:8]}"

        async with session_factory() as seed_session:
            repo = SlackRepository(seed_session)
            endpoint = await repo.get_endpoint(tenant_id)
            assert endpoint is not None

            seed_session.add(
                ChatThread(
                    id=chat_thread_id,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    agent_id=endpoint.agent_id,
                    title=f"Slack DM with U_{uuid4().hex[:8]}",
                    message_count=0,
                )
            )
            await seed_session.flush()
            await repo.create_thread_link(
                tenant_id=tenant_id,
                endpoint_id=endpoint.id,
                agent_id=endpoint.agent_id,
                external_user_id=f"U_{uuid4().hex[:8]}",
                external_channel_id=channel_id,
                chat_thread_id=chat_thread_id,
                external_thread_key="",
            )
            await seed_session.commit()

        async with session_factory() as delete_session:
            deleted = await ChatService(tenant_id, delete_session).delete_thread(chat_thread_id)
            await delete_session.commit()
            assert deleted is True

            link_count = await delete_session.scalar(
                select(func.count())
                .select_from(IngressThreadLink)
                .where(
                    IngressThreadLink.tenant_id == tenant_id,
                    IngressThreadLink.chat_thread_id == chat_thread_id,
                )
            )
            thread_count = await delete_session.scalar(
                select(func.count()).select_from(ChatThread).where(ChatThread.id == chat_thread_id)
            )

        assert link_count == 0
        assert thread_count == 0
