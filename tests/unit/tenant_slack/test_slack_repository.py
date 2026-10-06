"""Unit tests for SlackRepository reverse lookup."""

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
