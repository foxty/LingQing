"""E2E agent runtime via committed chat turn flow (real graph, stub LLM only)."""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import select

from apps.shared.db.models import AgentRunMessage, Tenant, ThreadMainMessage, User
from apps.shared.schemas.user import UserDTO
from apps.tenant_app_service.chat.domain import AgentRunStatus
from apps.tenant_app_service.chat.infrastructure.persistence.agent_run_repository import AgentRunRepository
from apps.tenant_app_service.chat.application.turn_flow import run_non_stream_chat_turn
from apps.tenant_app_service.chat.agent_run_port_adapter import ChatAgentRunPort
from apps.tenant_app_service.chat.schemas import ChatRequest, SimpleMessage
from tests.integration.helpers.agent_runtime_stub import patch_agent_base_stub_llm, patch_turn_session_end_noop
from tests.integration.test_thread_turn_admission_integration import _chat_post_body

pytestmark = pytest.mark.integration


async def _owner_dto(committed_chat_setup: dict) -> UserDTO:
    async with committed_chat_setup["session_local"]() as db:
        owner = await db.get(User, committed_chat_setup["owner_id"])
        assert owner is not None
        tenant = await db.get(Tenant, owner.tenant_id)
        tenant_name = tenant.name if tenant else "admission-tenant"
        return UserDTO(
            id=owner.id,
            username=owner.username,
            role=owner.role,
            tenant_id=owner.tenant_id,
            tenant_name=tenant_name,
        )


@pytest.mark.asyncio
async def test_run_non_stream_turn_wires_ports_and_persists_run(committed_chat_setup: dict, monkeypatch):
    """prepare → complete uses ``agent_run_port`` + real load/save nodes."""
    patch_agent_base_stub_llm(monkeypatch, content="runtime-e2e-ai")
    patch_turn_session_end_noop(monkeypatch)

    captured: list[dict] = []
    original_build = None

    from apps.tenant_app_service.chat.turn_service import ChatTurnService

    def _spy_build(self, *args, **kwargs):
        config = original_build(self, *args, **kwargs)
        if config.get("configurable", {}).get("run_id"):
            captured.append(config)
        return config

    original_build = ChatTurnService._build_runtime_config
    monkeypatch.setattr(ChatTurnService, "_build_runtime_config", _spy_build)

    user = await _owner_dto(committed_chat_setup)
    request = ChatRequest(
        tenant_id=committed_chat_setup["tenant_id"],
        agent_id=committed_chat_setup["agent_id"],
        thread_id=committed_chat_setup["thread_id"],
        message=SimpleMessage(role="human", content="runtime integration hello"),
    )

    response = await run_non_stream_chat_turn(committed_chat_setup["tenant_id"], request, user)
    assert "runtime-e2e-ai" in response.response.content
    assert captured, "expected _build_runtime_config with run_id during complete"
    port = captured[-1]["configurable"].get("agent_run_port")
    assert isinstance(port, ChatAgentRunPort)

    async with committed_chat_setup["session_local"]() as db:
        run = await AgentRunRepository(db).get_by_session_id(response.response.session_id)
        assert run is not None
        assert run.status == AgentRunStatus.COMPLETED

        ai_rows = await db.execute(
            select(AgentRunMessage).where(
                AgentRunMessage.run_id == run.id,
                AgentRunMessage.type == "ai",
            )
        )
        assert ai_rows.scalars().first() is not None

        promoted = await db.execute(
            select(ThreadMainMessage).where(
                ThreadMainMessage.thread_id == committed_chat_setup["thread_id"],
                ThreadMainMessage.type == "ai",
            )
        )
        assert promoted.scalars().first() is not None


@pytest.mark.asyncio
async def test_post_chat_http_same_runtime_path(committed_chat_setup: dict, monkeypatch):
    """HTTP POST /chat uses the same prepare/complete path (stub LLM)."""
    import httpx

    from apps.tenant_app_service.server import app

    patch_agent_base_stub_llm(monkeypatch, content="http-runtime-ai")
    patch_turn_session_end_noop(monkeypatch)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/chat",
            headers=committed_chat_setup["owner_headers"],
            json=_chat_post_body(committed_chat_setup, content=f"http-{uuid4().hex[:6]}"),
        )
    assert response.status_code == 200, response.text
    assert "http-runtime-ai" in response.json()["response"]["content"]
