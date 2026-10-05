"""Fake Slack Web API for integration tests.

Records chat.postMessage / users.info / auth.test / conversations.open calls
and returns canned responses. Also provides a signing-header generator so
tests can produce valid X-Slack-Signature headers for the webhook.

Patch apps.tenant_app_service.agent_ingress.slack.client.SlackWebClient methods (or inject
this via the SlackClientPort) to mock the Slack HTTP boundary without touching
real network.
"""

from __future__ import annotations

import hashlib
import hmac
import time
from typing import Any


class FakeSlackClient:
    """In-memory Slack Web API adapter implementing SlackClientPort."""

    def __init__(self):
        self.posted_messages: list[dict[str, Any]] = []
        self.updated_messages: list[dict[str, Any]] = []
        self.opened_conversations: list[dict[str, Any]] = []
        self.auth_test_results: dict[str, dict[str, Any]] = {}
        self.users: dict[str, dict[str, Any]] = {}
        # default auth.test success
        self.default_auth_ok = True

    # ---------- SlackClientPort implementation ----------

    async def auth_test(self, *, bot_token: str) -> dict[str, Any]:
        result = self.auth_test_results.get(bot_token)
        if result:
            return result
        if self.default_auth_ok:
            return {
                "ok": True,
                "team_id": "T_FAKE",
                "team": "Fake Workspace",
                "user_id": "U_BOT",
                "api_app_id": "A_FAKE",
            }
        return {"ok": False, "error": "invalid_auth"}

    async def users_info(self, *, bot_token: str, user_id: str) -> dict[str, Any] | None:
        user = self.users.get(user_id)
        if not user:
            return None
        return {"id": user_id, "name": user.get("name", user_id), "profile": user.get("profile", {})}

    async def chat_post_message(
        self,
        *,
        bot_token: str,
        channel: str,
        text: str,
        thread_ts: str | None = None,
        blocks: list[dict] | None = None,
    ) -> dict[str, Any]:
        ts = f"{len(self.posted_messages) + 1}.000000"
        record = {"channel": channel, "text": text, "thread_ts": thread_ts, "blocks": blocks, "ts": ts}
        self.posted_messages.append(record)
        return {"ok": True, "ts": ts, "channel": channel}

    async def chat_update(
        self,
        *,
        bot_token: str,
        channel: str,
        ts: str,
        text: str,
        blocks: list[dict] | None = None,
    ) -> dict[str, Any]:
        record = {"channel": channel, "ts": ts, "text": text, "blocks": blocks}
        self.updated_messages.append(record)
        return {"ok": True}

    async def conversations_open(self, *, bot_token: str, users: str) -> dict[str, Any]:
        channel_id = f"D_{users}"
        self.opened_conversations.append({"users": users, "channel": channel_id})
        return {"ok": True, "channel": {"id": channel_id}}

    # ---------- Test helpers ----------

    def register_user(self, user_id: str, *, email: str | None, display_name: str | None = None):
        self.users[user_id] = {
            "name": display_name or user_id,
            "profile": {"email": email, "display_name": display_name or user_id},
        }

    def set_auth_test_result(self, bot_token: str, *, ok: bool, **extra):
        result = {"ok": ok}
        result.update(extra)
        self.auth_test_results[bot_token] = result


def make_slack_signature_headers(
    *,
    signing_secret: str,
    body: str,
    timestamp: int | None = None,
) -> dict[str, str]:
    """Produce valid X-Slack-Signature + X-Slack-Request-Timestamp headers."""
    ts = str(timestamp if timestamp is not None else int(time.time()))
    base = f"v0:{ts}:{body}"
    signature = "v0=" + hmac.new(
        signing_secret.encode("utf-8"), base.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    return {
        "X-Slack-Signature": signature,
        "X-Slack-Request-Timestamp": ts,
        "Content-Type": "application/json",
    }
