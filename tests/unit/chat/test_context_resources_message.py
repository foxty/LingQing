"""Tests for @mention context resource injection in chat."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import HumanMessage, SystemMessage

from apps.shared.context_resource.domain import ContextResourceItem
from apps.tenant_app_service.chat.schemas import ContextResourceRef
from apps.tenant_app_service.chat.service import ChatService


@pytest.fixture
def chat_service():
    return ChatService(tenant_id=2, db=MagicMock())


def _mock_resolve(items: list[ContextResourceItem]):
    mock_service = MagicMock()
    mock_service.resolve_by_refs = AsyncMock(return_value=items)
    return patch(
        "apps.tenant_app_service.chat.service.ContextResourceSearchService",
        return_value=mock_service,
    )


@pytest.mark.asyncio
async def test_prepare_context_resources_message_accepts_pydantic_refs(chat_service):
    items = [
        ContextResourceItem(
            resource_type="document",
            resource_id=2,
            title="sample-report-acme.pdf",
        )
    ]
    with _mock_resolve(items):
        refs = [ContextResourceRef(resource_type="document", resource_id=2)]
        message = await chat_service._prepare_context_resources_message(refs)

    assert isinstance(message, SystemMessage)
    assert "sample-report-acme.pdf" in message.content
    assert "Type: document" in message.content
    assert "attached the following resources" in message.content


@pytest.mark.asyncio
async def test_inject_selected_context_resources_stamps_human_message(chat_service):
    items = [
        ContextResourceItem(
            resource_type="document",
            resource_id=2,
            title="sample-report-acme.pdf",
        )
    ]
    human = HumanMessage(id="human-1", content="what is this?")
    refs = [ContextResourceRef(resource_type="document", resource_id=2)]

    with _mock_resolve(items):
        messages = await chat_service._inject_selected_context_resources(
            [human],
            refs,
            thread_id="thread-1",
            selected_artifact_id=None,
        )

    assert isinstance(messages[0], SystemMessage)
    assert messages[1] is human
    assert human.additional_kwargs["context_resources"] == [
        {
            "resource_type": "document",
            "resource_id": 2,
            "title": "sample-report-acme.pdf",
            "subtitle": None,
        }
    ]


@pytest.mark.asyncio
async def test_prepare_context_resources_message_scopes_asset_by_data_source_tenant(
    chat_service,
):
    items = [
        ContextResourceItem(
            resource_type="asset",
            resource_id=9,
            title="sales_orders",
            subtitle="Databricks",
        )
    ]
    with _mock_resolve(items):
        refs = [ContextResourceRef(resource_type="asset", resource_id=9)]
        message = await chat_service._prepare_context_resources_message(refs)

    assert isinstance(message, SystemMessage)
    assert "Type: asset, Title: sales_orders, Data Source: Databricks" in message.content


@pytest.mark.asyncio
async def test_prepare_context_resources_message_marks_missing_resource(chat_service):
    items = [
        ContextResourceItem(
            resource_type="dashboard",
            resource_id=404,
            title="dashboard #404",
            subtitle="not found",
        )
    ]
    with _mock_resolve(items):
        refs = [ContextResourceRef(resource_type="dashboard", resource_id=404)]
        message = await chat_service._prepare_context_resources_message(refs)

    assert isinstance(message, SystemMessage)
    assert "dashboard (id=404): not found" in message.content
