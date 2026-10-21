"""Integration tests for Slack channel/group chat ingress."""

import asyncio
import json
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from tests.slack.fake_slack import make_slack_signature_headers
from tests.slack.slack_event_factory import (
    make_app_mention_event,
    make_channel_thread_reply_event,
    make_event_callback_payload,
    make_message_event,
)


async def _wait_for_slack_side_effect(check, *, timeout_seconds: float = 8.0) -> None:
    deadline = asyncio.get_event_loop().time() + timeout_seconds
    last_error = None
    while asyncio.get_event_loop().time() < deadline:
        try:
            await check()
            return
        except AssertionError as exc:
            last_error = exc
            await asyncio.sleep(0.1)
    if last_error is not None:
        raise last_error
    raise AssertionError("Slack side effect not observed before timeout")


class TestSlackChannelWebhook:
    @pytest.mark.asyncio
    async def test_app_mention_in_channel_accepted(self, slack_committed_chat_setup):
        client = slack_committed_chat_setup["client"]
        tenant = slack_committed_chat_setup["tenants"]["tenant_a"]
        signing_secret = slack_committed_chat_setup["secrets"]["tenant_a"]
        fake = slack_committed_chat_setup["fake_slack"]
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
            f"/ingress/{slack_committed_chat_setup['endpoint_keys']['tenant_a']}/events",
            content=body,
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

        async def _assert_thinking_posted() -> None:
            assert fake.posted_messages, "expected bot to post thinking placeholder in channel thread"
            assert fake.posted_messages[0]["thread_ts"] == "1700000000.000100"

        await _wait_for_slack_side_effect(_assert_thinking_posted)

    @pytest.mark.asyncio
    async def test_thread_follow_up_without_mention_is_ignored(self, slack_test_setup):
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
        assert resp.json()["status"] == "ignored"
        await asyncio.sleep(0.5)
        assert not fake.posted_messages
        assert not fake.updated_messages

    @pytest.mark.asyncio
    async def test_thread_reply_mentioning_other_user_is_ignored(self, slack_test_setup):
        client = slack_test_setup["client"]
        tenant = slack_test_setup["tenants"]["tenant_a"]
        signing_secret = slack_test_setup["secrets"]["tenant_a"]
        fake = slack_test_setup["fake_slack"]
        slack_user = f"U_peer_{uuid4().hex[:8]}"
        fake.register_user(slack_user, email=tenant["admin"].email)
        fake.posted_messages.clear()
        fake.updated_messages.clear()

        event = make_channel_thread_reply_event(
            user_id=slack_user,
            channel_id=f"C_peer_{uuid4().hex[:8]}",
            text="<@U_COLLEAGUE> FYI on this thread",
            thread_ts="1700000099.000200",
            team_id="T_TENANT_A",
        )
        payload = make_event_callback_payload(event=event, event_id=f"Ev_peer_{slack_user}", team_id="T_TENANT_A")
        body = json.dumps(payload)
        headers = make_slack_signature_headers(signing_secret=signing_secret, body=body)
        resp = await client.post(
            f"/ingress/{slack_test_setup['endpoint_keys']['tenant_a']}/events",
            content=body,
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ignored"
        await asyncio.sleep(0.5)
        assert not fake.posted_messages
        assert not fake.updated_messages

    @pytest.mark.asyncio
    async def test_app_mention_with_duplicate_message_event_runs_agent_once(
        self, slack_test_setup, monkeypatch
    ):
        client = slack_test_setup["client"]
        tenant = slack_test_setup["tenants"]["tenant_a"]
        signing_secret = slack_test_setup["secrets"]["tenant_a"]
        fake = slack_test_setup["fake_slack"]
        slack_user = f"U_dedupe_{uuid4().hex[:8]}"
        channel_id = f"C_dedupe_{uuid4().hex[:8]}"
        thread_root = "1700000000.000700"
        message_ts = "1700000000.000701"
        fake.register_user(slack_user, email=tenant["admin"].email)
        fake.posted_messages.clear()
        fake.updated_messages.clear()

        from tests.slack.chat_turn_mock import default_chat_response, patch_slack_chat_turn

        chat_calls: dict[str, int] = {"count": 0}

        def on_complete(_self, _request, _user, _prepared, **_kwargs):
            chat_calls["count"] += 1
            return default_chat_response()

        patch_slack_chat_turn(on_complete=on_complete)

        mention = make_app_mention_event(
            user_id=slack_user,
            channel_id=channel_id,
            text="<@UBOT> one request",
            team_id="T_TENANT_A",
            thread_ts=thread_root,
            ts=message_ts,
        )
        duplicate_message = make_channel_thread_reply_event(
            user_id=slack_user,
            channel_id=channel_id,
            text="<@UBOT> one request",
            thread_ts=thread_root,
            team_id="T_TENANT_A",
            ts=message_ts,
        )
        url = f"/ingress/{slack_test_setup['endpoint_keys']['tenant_a']}/events"

        mention_body = json.dumps(
            make_event_callback_payload(event=mention, event_id=f"Ev_dedupe_m_{slack_user}", team_id="T_TENANT_A")
        )
        message_body = json.dumps(
            make_event_callback_payload(
                event=duplicate_message,
                event_id=f"Ev_dedupe_msg_{slack_user}",
                team_id="T_TENANT_A",
            )
        )
        headers_mention = make_slack_signature_headers(signing_secret=signing_secret, body=mention_body)
        headers_message = make_slack_signature_headers(signing_secret=signing_secret, body=message_body)

        resp1 = await client.post(url, content=mention_body, headers=headers_mention)
        resp2 = await client.post(url, content=message_body, headers=headers_message)
        assert resp1.status_code == 200
        assert resp1.json()["status"] == "ok"
        assert resp2.status_code == 200
        assert resp2.json()["status"] == "ignored"

        await asyncio.sleep(0.5)
        assert chat_calls["count"] == 1

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
    async def test_thread_follow_up_with_mention_continues_existing_channel_thread(
        self, slack_committed_chat_setup, monkeypatch
    ):
        client = slack_committed_chat_setup["client"]
        tenant = slack_committed_chat_setup["tenants"]["tenant_a"]
        signing_secret = slack_committed_chat_setup["secrets"]["tenant_a"]
        fake = slack_committed_chat_setup["fake_slack"]
        slack_user = f"U_cont_{uuid4().hex[:8]}"
        channel_id = f"C_cont_{uuid4().hex[:8]}"
        thread_root = "1700000000.000500"
        fake.register_user(slack_user, email=tenant["admin"].email)

        from apps.tenant_app_service.agent_ingress.slack import chat_turn_flow

        prepare_thread_ids: list[str] = []
        real_prepare = chat_turn_flow.prepare_chat_turn_committed

        async def _track_prepare(tenant_id, request, current_user, **kwargs):
            prepare_thread_ids.append(request.thread_id)
            return await real_prepare(tenant_id, request, current_user, **kwargs)

        monkeypatch.setattr(chat_turn_flow, "prepare_chat_turn_committed", _track_prepare)

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
        url = f"/ingress/{slack_committed_chat_setup['endpoint_keys']['tenant_a']}/events"
        resp1 = await client.post(url, content=mention_body, headers=headers)
        assert resp1.status_code == 200

        async def _assert_first_prepare_finished() -> None:
            assert len(prepare_thread_ids) == 1

        await _wait_for_slack_side_effect(_assert_first_prepare_finished)
        fake.posted_messages.clear()
        fake.updated_messages.clear()

        follow_up = make_app_mention_event(
            user_id=slack_user,
            channel_id=channel_id,
            text="<@UBOT> continue please",
            thread_ts=thread_root,
            team_id="T_TENANT_A",
            ts="1700000000.000600",
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

        async def _assert_second_prepare_reuses_thread() -> None:
            assert len(prepare_thread_ids) == 2
            assert prepare_thread_ids[0] == prepare_thread_ids[1]

        await _wait_for_slack_side_effect(_assert_second_prepare_reuses_thread)

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
        assert any("No LingQing account" in m["text"] for m in fake.ephemeral_messages)


class TestSlackSharedThreadIngress:
    @pytest.mark.asyncio
    async def test_channel_app_mention_creates_shared_thread_and_link(self, slack_committed_chat_setup):
        from sqlalchemy import select

        from apps.shared.db.models import ChatThread, IngressThreadLink

        client = slack_committed_chat_setup["client"]
        tenant = slack_committed_chat_setup["tenants"]["tenant_a"]
        signing_secret = slack_committed_chat_setup["secrets"]["tenant_a"]
        session_factory = slack_committed_chat_setup["session_factory"]
        fake = slack_committed_chat_setup["fake_slack"]
        slack_user = f"U_shared_{uuid4().hex[:8]}"
        channel_id = f"C_shared_{uuid4().hex[:8]}"
        thread_root = "1700000010.000100"
        fake.register_user(slack_user, email=tenant["admin"].email)

        event = make_app_mention_event(
            user_id=slack_user,
            channel_id=channel_id,
            text="<@UBOT> bootstrap shared",
            team_id="T_TENANT_A",
            ts=thread_root,
        )
        body = json.dumps(
            make_event_callback_payload(event=event, event_id=f"Ev_shared_{slack_user}", team_id="T_TENANT_A")
        )
        headers = make_slack_signature_headers(signing_secret=signing_secret, body=body)
        url = f"/ingress/{slack_committed_chat_setup['endpoint_keys']['tenant_a']}/events"
        resp = await client.post(url, content=body, headers=headers)
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

        tenant_id = tenant["tenant"].id

        async def _assert_shared_mapping() -> None:
            async with session_factory() as session:
                link = await session.scalar(
                    select(IngressThreadLink).where(
                        IngressThreadLink.tenant_id == tenant_id,
                        IngressThreadLink.external_channel_id == channel_id,
                        IngressThreadLink.external_thread_key == thread_root,
                    )
                )
                assert link is not None
                thread = await session.get(ChatThread, link.chat_thread_id)
                assert thread is not None
                assert thread.thread_kind == "shared"

        await _wait_for_slack_side_effect(_assert_shared_mapping)

    @pytest.mark.asyncio
    async def test_passive_mirror_persists_thread_reply_after_anchor(self, slack_committed_chat_setup):
        from sqlalchemy import select

        from apps.shared.db.models import ChatMessage, IngressThreadLink

        client = slack_committed_chat_setup["client"]
        tenant = slack_committed_chat_setup["tenants"]["tenant_a"]
        signing_secret = slack_committed_chat_setup["secrets"]["tenant_a"]
        session_factory = slack_committed_chat_setup["session_factory"]
        fake = slack_committed_chat_setup["fake_slack"]
        slack_user = f"U_mirror_{uuid4().hex[:8]}"
        channel_id = f"C_mirror_{uuid4().hex[:8]}"
        thread_root = "1700000020.000100"
        passive_ts = "1700000020.000200"
        fake.register_user(slack_user, email=tenant["admin"].email)

        url = f"/ingress/{slack_committed_chat_setup['endpoint_keys']['tenant_a']}/events"
        mention = make_app_mention_event(
            user_id=slack_user,
            channel_id=channel_id,
            text="<@UBOT> open mirror",
            team_id="T_TENANT_A",
            ts=thread_root,
        )
        mention_body = json.dumps(
            make_event_callback_payload(event=mention, event_id=f"Ev_mirror_m_{slack_user}", team_id="T_TENANT_A")
        )
        await client.post(
            url,
            content=mention_body,
            headers=make_slack_signature_headers(signing_secret=signing_secret, body=mention_body),
        )

        reply = make_channel_thread_reply_event(
            user_id=slack_user,
            channel_id=channel_id,
            text="team update without bot",
            thread_ts=thread_root,
            team_id="T_TENANT_A",
            ts=passive_ts,
        )
        reply_body = json.dumps(
            make_event_callback_payload(event=reply, event_id=f"Ev_mirror_r_{slack_user}", team_id="T_TENANT_A")
        )
        resp = await client.post(
            url,
            content=reply_body,
            headers=make_slack_signature_headers(signing_secret=signing_secret, body=reply_body),
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

        async def _assert_room_message() -> None:
            async with session_factory() as session:
                link = await session.scalar(
                    select(IngressThreadLink).where(
                        IngressThreadLink.external_channel_id == channel_id,
                        IngressThreadLink.external_thread_key == thread_root,
                    )
                )
                assert link is not None
                row = await session.scalar(
                    select(ChatMessage).where(ChatMessage.message_id == f"slack_passive_{passive_ts}")
                )
                assert row is not None
                assert row.content == "team update without bot"
                assert (row.message_metadata or {}).get("interaction") == "room_message"

        await _wait_for_slack_side_effect(_assert_room_message)

    @pytest.mark.asyncio
    async def test_second_slack_user_joins_shared_thread_membership(self, slack_committed_chat_setup):
        from sqlalchemy import func, select

        from apps.shared.db.models import ChatThreadUserMember, IngressThreadLink, TenantMembership, User

        client = slack_committed_chat_setup["client"]
        tenant = slack_committed_chat_setup["tenants"]["tenant_a"]
        signing_secret = slack_committed_chat_setup["secrets"]["tenant_a"]
        session_factory = slack_committed_chat_setup["session_factory"]
        fake = slack_committed_chat_setup["fake_slack"]
        tenant_id = tenant["tenant"].id
        email_domain = tenant["admin"].email.split("@", 1)[1]
        channel_id = f"C_member_{uuid4().hex[:8]}"
        thread_root = "1700000030.000100"

        slack_user_a = f"U_mem_a_{uuid4().hex[:8]}"
        slack_user_b = f"U_mem_b_{uuid4().hex[:8]}"
        fake.register_user(slack_user_a, email=tenant["admin"].email)

        async with session_factory() as session:
            member = User(
                username=f"member_{uuid4().hex[:8]}",
                email=f"member_{uuid4().hex[:8]}@{email_domain}",
                hashed_password="$2b$12$dummy",
                tenant_id=tenant_id,
                role="member",
            )
            session.add(member)
            await session.flush()
            session.add(TenantMembership(tenant_id=tenant_id, user_id=member.id, status="active"))
            await session.commit()
            member_email = member.email

        fake.register_user(slack_user_b, email=member_email)

        url = f"/ingress/{slack_committed_chat_setup['endpoint_keys']['tenant_a']}/events"
        first = make_app_mention_event(
            user_id=slack_user_a,
            channel_id=channel_id,
            text="<@UBOT> first user",
            team_id="T_TENANT_A",
            ts=thread_root,
        )
        first_body = json.dumps(
            make_event_callback_payload(event=first, event_id=f"Ev_mem_a_{slack_user_a}", team_id="T_TENANT_A")
        )
        await client.post(
            url,
            content=first_body,
            headers=make_slack_signature_headers(signing_secret=signing_secret, body=first_body),
        )

        second = make_app_mention_event(
            user_id=slack_user_b,
            channel_id=channel_id,
            text="<@UBOT> second user",
            thread_ts=thread_root,
            team_id="T_TENANT_A",
            ts="1700000030.000200",
        )
        second_body = json.dumps(
            make_event_callback_payload(event=second, event_id=f"Ev_mem_b_{slack_user_b}", team_id="T_TENANT_A")
        )
        resp = await client.post(
            url,
            content=second_body,
            headers=make_slack_signature_headers(signing_secret=signing_secret, body=second_body),
        )
        assert resp.status_code == 200

        async def _assert_two_members() -> None:
            async with session_factory() as session:
                link = await session.scalar(
                    select(IngressThreadLink).where(
                        IngressThreadLink.external_channel_id == channel_id,
                        IngressThreadLink.external_thread_key == thread_root,
                    )
                )
                assert link is not None
                count = await session.scalar(
                    select(func.count())
                    .select_from(ChatThreadUserMember)
                    .where(ChatThreadUserMember.thread_id == link.chat_thread_id)
                )
                assert count is not None and count >= 2

        await _wait_for_slack_side_effect(_assert_two_members)
