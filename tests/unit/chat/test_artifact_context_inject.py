"""Tests for @mention artifact injection in chat."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import HumanMessage, SystemMessage

from apps.shared.schemas.user import UserDTO
from apps.tenant_app_service.chat.service import ChatService


@pytest.fixture
def chat_service():
    return ChatService(tenant_id=1, db=MagicMock())


@pytest.mark.asyncio
async def test_inject_selected_artifacts_stamps_human_message(chat_service, monkeypatch):
    mock_record = MagicMock()
    mock_record.artifact_type = "report"
    mock_record.id = 5
    mock_record.resource_id = 88
    mock_record.url = "/reports/88/embed"
    mock_record.title = "Q1 Report"
    mock_record.tenant_id = 1
    mock_record.owner_id = 1
    mock_record.artifact_metadata = {}
    mock_record.created_at = None
    mock_record.updated_at = None
    mock_record.source_thread_id = None
    mock_record.owner_user = None

    monkeypatch.setattr(
        "apps.shared.artifact.access.require_artifact_record_read",
        AsyncMock(return_value=mock_record),
    )

    human = HumanMessage(id="h1", content="continue this report")
    user = UserDTO(id=1, username="admin", role="admin", tenant_id=1, tenant_name="T")

    messages = await chat_service._inject_selected_artifacts(
        [human],
        [5],
        current_user=user,
    )

    assert isinstance(messages[0], SystemMessage)
    assert "Q1 Report" in messages[0].content
    assert human.additional_kwargs["attached_artifacts"][0]["artifact_id"] == 5
