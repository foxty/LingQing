"""Tests for @mention artifact injection in chat."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from langchain_core.messages import HumanMessage, SystemMessage

from apps.shared.schemas.user import UserDTO
from apps.tenant_app_service.chat.service import ChatService
from tests.helpers.artifact_access_fixtures import create_standalone_artifact, create_tenant_with_users


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


@pytest.mark.asyncio
async def test_inject_message_attachments_prefers_selected_artifact_ids(monkeypatch):
    service = ChatService(tenant_id=1, db=MagicMock())
    captured: list[list[int]] = []

    async def _capture(_msgs, ids, *, current_user):
        captured.append(ids)
        return _msgs

    monkeypatch.setattr(service, "_inject_selected_artifacts", _capture)
    human = HumanMessage(content="hi")
    user = UserDTO(id=1, username="u", role="member", tenant_id=1, tenant_name="T")

    await service._inject_message_attachments(
        [human],
        selected_artifact_ids=[10, 11],
        selected_artifact_id=99,
        current_user=user,
    )
    assert captured == [[10, 11]]


@pytest.mark.asyncio
async def test_inject_message_attachments_legacy_single_id(monkeypatch):
    service = ChatService(tenant_id=1, db=MagicMock())
    captured: list[list[int]] = []

    async def _capture(_msgs, ids, *, current_user):
        captured.append(ids)
        return _msgs

    monkeypatch.setattr(service, "_inject_selected_artifacts", _capture)
    user = UserDTO(id=1, username="u", role="member", tenant_id=1, tenant_name="T")

    await service._inject_message_attachments(
        [HumanMessage(content="hi")],
        selected_artifact_id=42,
        current_user=user,
    )
    assert captured == [[42]]


@pytest.mark.asyncio
async def test_inject_selected_artifacts_skips_inaccessible_with_placeholder(chat_service, monkeypatch):
    monkeypatch.setattr(
        "apps.shared.artifact.access.require_artifact_record_read",
        AsyncMock(side_effect=Exception("denied")),
    )
    human = HumanMessage(id="h2", content="try bad artifact")
    user = UserDTO(id=2, username="peer", role="member", tenant_id=1, tenant_name="T")

    messages = await chat_service._inject_selected_artifacts([human], [404], current_user=user)

    assert isinstance(messages[0], SystemMessage)
    assert "not accessible" in messages[0].content
    assert human.additional_kwargs["attached_artifacts"][0]["artifact_id"] == 404


@pytest.mark.asyncio
async def test_inject_selected_artifacts_with_real_db(async_db_session):
    suffix = uuid4().hex[:8]
    tenant, owner, peer = await create_tenant_with_users(
        async_db_session,
        owner_username=f"inj_owner_{suffix}",
        peer_username=f"inj_peer_{suffix}",
    )
    artifact = await create_standalone_artifact(
        async_db_session,
        tenant_id=tenant.id,
        owner_id=owner.id,
        resource_id=3001,
        title="Inject Me",
    )
    service = ChatService(tenant_id=tenant.id, db=async_db_session)
    owner_dto = UserDTO(
        id=owner.id,
        username=owner.username,
        role=owner.role,
        tenant_id=tenant.id,
        tenant_name=tenant.name,
    )
    human = HumanMessage(content="continue")
    messages = await service._inject_selected_artifacts(
        [human],
        [artifact.id],
        current_user=owner_dto,
    )
    assert "Inject Me" in messages[0].content
    assert human.additional_kwargs["attached_artifacts"][0]["artifact_id"] == artifact.id

    peer_dto = UserDTO(
        id=peer.id,
        username=peer.username,
        role=peer.role,
        tenant_id=tenant.id,
        tenant_name=tenant.name,
    )
    peer_human = HumanMessage(content="sneak")
    peer_messages = await service._inject_selected_artifacts(
        [peer_human],
        [artifact.id],
        current_user=peer_dto,
    )
    assert "not accessible" in peer_messages[0].content
