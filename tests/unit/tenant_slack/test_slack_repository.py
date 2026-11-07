"""Unit tests for SlackRepository reverse lookup."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from apps.tenant_app_service.agent_ingress.slack.repository import SlackRepository


@pytest.mark.asyncio
async def test_get_conversation_mapping_by_thread_id():
    mapping = MagicMock()
    db = AsyncMock()
    db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=mapping)))

    repo = SlackRepository(db)
    result = await repo.get_thread_link_by_chat_thread_id(1, "thread_abc")

    assert result is mapping
    db.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_endpoint_stores_channel_chat_flag_without_changing_scope():
    endpoint = SimpleNamespace(
        credentials_encrypted={},
        platform_config={"team_id": "T1", "app_id": "A1"},
        tenant_id=3,
        external_scope_key="slack:T1:A1",
        enabled=True,
        agent_id=9,
    )
    repo = SlackRepository(AsyncMock())

    updated = await repo.update_endpoint(endpoint, channel_chat_enabled=False)

    assert updated.platform_config["channel_chat_enabled"] is False
    assert updated.platform_config["team_id"] == "T1"
    assert updated.external_scope_key == "slack:T1:A1"
