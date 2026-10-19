"""Tests for Slack file upload readiness polling."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from slack_sdk.errors import SlackApiError

from apps.tenant_app_service.agent_ingress.slack.client import wait_for_slack_file_ready


@pytest.mark.asyncio
async def test_wait_for_slack_file_ready_returns_when_mimetype_populated():
    client = MagicMock()
    pending = MagicMock(data={"file": {"id": "F1", "mimetype": "", "filetype": ""}})
    ready = MagicMock(data={"file": {"id": "F1", "mimetype": "image/png", "filetype": "png"}})
    client.files_info = AsyncMock(side_effect=[pending, ready])

    await wait_for_slack_file_ready(client, "F1", timeout_seconds=2.0, poll_interval_seconds=0.01)

    assert client.files_info.await_count == 2


@pytest.mark.asyncio
async def test_wait_for_slack_file_ready_exits_on_missing_scope():
    client = MagicMock()
    client.files_info = AsyncMock(
        side_effect=SlackApiError("missing scope", {"error": "missing_scope", "needed": "files:read"})
    )

    await wait_for_slack_file_ready(client, "F1", timeout_seconds=1.0, poll_interval_seconds=0.01)

    assert client.files_info.await_count == 1
