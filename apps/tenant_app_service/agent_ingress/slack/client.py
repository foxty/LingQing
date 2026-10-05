"""Slack Web API client adapter.

The only place that calls Slack HTTP. Defines SlackClientPort protocol so
unit/integration tests can mock the HTTP boundary, not domain logic.
"""

from __future__ import annotations

from typing import Any, Protocol

from slack_sdk.errors import SlackApiError
from slack_sdk.web.async_client import AsyncWebClient

from apps.shared.utils.logger import get_logger

logger = get_logger(__name__)


class SlackClientPort(Protocol):
    """Port for Slack Web API calls. Implementations must be async."""

    async def auth_test(self, *, bot_token: str) -> dict[str, Any]:
        """Validate the bot token and return team info."""
        ...

    async def users_info(self, *, bot_token: str, user_id: str) -> dict[str, Any] | None:
        """Fetch a Slack user's profile (email, display_name)."""
        ...

    async def chat_post_message(
        self,
        *,
        bot_token: str,
        channel: str,
        text: str,
        thread_ts: str | None = None,
        blocks: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Post a message to a channel, optionally threaded."""
        ...

    async def chat_update(
        self,
        *,
        bot_token: str,
        channel: str,
        ts: str,
        text: str,
        blocks: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Update a previously posted message (thinking -> final reply)."""
        ...

    async def views_open(self, *, bot_token: str, trigger_id: str, view: dict[str, Any]) -> dict[str, Any]:
        """Open a modal view."""
        ...

    async def conversations_open(self, *, bot_token: str, users: str) -> dict[str, Any]:
        """Open a DM channel with one or more users."""
        ...


class SlackWebClient:
    """Production Slack Web API adapter backed by slack-sdk AsyncWebClient."""

    async def auth_test(self, *, bot_token: str) -> dict[str, Any]:
        client = AsyncWebClient(token=bot_token)
        try:
            resp = await client.auth_test()
            return dict(resp.data or {})
        except SlackApiError as exc:
            logger.warning("Slack auth.test failed: %s", exc)
            return {"ok": False, "error": str(exc.response.get("error") if exc.response else exc)}

    async def users_info(self, *, bot_token: str, user_id: str) -> dict[str, Any] | None:
        client = AsyncWebClient(token=bot_token)
        try:
            resp = await client.users_info(user=user_id)
            user = resp.data.get("user") if resp.data else None
            return dict(user) if user else None
        except SlackApiError as exc:
            logger.warning("Slack users.info failed for %s: %s", user_id, exc)
            return None

    async def chat_post_message(
        self,
        *,
        bot_token: str,
        channel: str,
        text: str,
        thread_ts: str | None = None,
        blocks: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        client = AsyncWebClient(token=bot_token)
        kwargs: dict[str, Any] = {"channel": channel, "text": text}
        if thread_ts:
            kwargs["thread_ts"] = thread_ts
        if blocks:
            kwargs["blocks"] = blocks
        resp = await client.chat_postMessage(**kwargs)
        return dict(resp.data or {})

    async def chat_update(
        self,
        *,
        bot_token: str,
        channel: str,
        ts: str,
        text: str,
        blocks: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        client = AsyncWebClient(token=bot_token)
        kwargs: dict[str, Any] = {"channel": channel, "ts": ts, "text": text}
        if blocks:
            kwargs["blocks"] = blocks
        resp = await client.chat_update(**kwargs)
        return dict(resp.data or {})

    async def views_open(self, *, bot_token: str, trigger_id: str, view: dict[str, Any]) -> dict[str, Any]:
        client = AsyncWebClient(token=bot_token)
        resp = await client.views_open(trigger_id=trigger_id, view=view)
        return dict(resp.data or {})

    async def conversations_open(self, *, bot_token: str, users: str) -> dict[str, Any]:
        client = AsyncWebClient(token=bot_token)
        resp = await client.conversations_open(users=users)
        return dict(resp.data or {})
