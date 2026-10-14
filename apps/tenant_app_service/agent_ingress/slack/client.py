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


def _slack_response_dict(exc: SlackApiError) -> dict[str, Any]:
    response = exc.response
    if isinstance(response, dict):
        return response
    if isinstance(response, str):
        return {"error": response}
    getter = getattr(response, "get", None)
    return dict(response) if callable(getter) else {}


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

    async def upload_file(self, *, bot_token: str, filename: str, content: bytes) -> str:
        """Upload image bytes and return the Slack file id for Block Kit ``slack_file`` blocks.

        Do not pass ``channel`` here — sharing the file into the channel creates a second
        message; the image block on ``chat.postMessage`` / ``chat.update`` references the id.
        """
        ...

    async def create_canvas(self, *, bot_token: str, title: str, markdown: str) -> str:
        """Create a Slack Canvas from GFM Markdown and return its id."""
        ...

    async def grant_canvas_read(
        self,
        *,
        bot_token: str,
        canvas_id: str,
        channel_id: str | None = None,
        user_id: str | None = None,
    ) -> None:
        """Grant read access to a Canvas for one channel or one user."""
        ...

    async def canvas_permalink(self, *, bot_token: str, canvas_id: str) -> str:
        """Return the permalink for a Canvas file."""
        ...

    async def file_permalink(self, *, bot_token: str, file_id: str) -> str | None:
        """Return a Slack file permalink suitable for Canvas markdown."""
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

    async def upload_file(self, *, bot_token: str, filename: str, content: bytes) -> str:
        client = AsyncWebClient(token=bot_token)
        resp = await client.files_upload_v2(filename=filename, content=content)
        return _file_id(dict(resp.data or {}))

    async def create_canvas(self, *, bot_token: str, title: str, markdown: str) -> str:
        client = AsyncWebClient(token=bot_token)
        resp = await client.canvases_create(
            title=title,
            document_content={"type": "markdown", "markdown": markdown},
        )
        data = dict(resp.data or {})
        canvas_id = data.get("canvas_id")
        if not canvas_id:
            raise SlackApiError("canvas_id missing", data)
        return str(canvas_id)

    async def grant_canvas_read(
        self,
        *,
        bot_token: str,
        canvas_id: str,
        channel_id: str | None = None,
        user_id: str | None = None,
    ) -> None:
        client = AsyncWebClient(token=bot_token)
        if user_id:
            await client.canvases_access_set(canvas_id=canvas_id, access_level="read", user_ids=[user_id])
            return
        if not channel_id:
            raise SlackApiError("canvas access target missing", {"error": "invalid_arguments"})
        await client.canvases_access_set(canvas_id=canvas_id, access_level="read", channel_ids=[channel_id])

    async def canvas_permalink(self, *, bot_token: str, canvas_id: str) -> str:
        client = AsyncWebClient(token=bot_token)
        resp = await client.files_info(file=canvas_id)
        data = dict(resp.data or {})
        permalink = (data.get("file") or {}).get("permalink")
        if not permalink:
            raise SlackApiError("canvas permalink missing", data)
        return str(permalink)

    async def file_permalink(self, *, bot_token: str, file_id: str) -> str | None:
        client = AsyncWebClient(token=bot_token)
        try:
            resp = await client.files_info(file=file_id)
        except SlackApiError as exc:
            payload = _slack_response_dict(exc)
            if payload.get("error") == "missing_scope" and payload.get("needed") == "files:read":
                logger.warning(
                    "Slack bot token is missing files:read (file=%s). "
                    "Add files:read under OAuth scopes and reinstall the app to the workspace.",
                    file_id,
                )
            else:
                logger.warning("Slack files.info failed for %s: %s", file_id, exc)
            return None
        file_obj = dict(resp.data or {}).get("file") or {}
        return file_obj.get("permalink") or file_obj.get("url_private")


def _file_id(data: dict[str, Any]) -> str:
    file_obj = data.get("file") or {}
    file_id = file_obj.get("id")
    if not file_id:
        files = data.get("files") or []
        if files:
            file_id = files[0].get("id")
    if not file_id:
        raise SlackApiError("file id missing", data)
    return str(file_id)
