"""Unit tests for custom-agent graph loading in ChatTurnService."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from apps.shared.domain.types import ABAC_ACTION_READ
from apps.shared.schemas.user import UserDTO
from apps.tenant_app_service.agent_catalog.domain import AgentCapabilityProfile, CustomAgent
from apps.tenant_app_service.chat.turn_service import ChatTurnService


def _custom_agent(*, agent_id: int = 9001) -> CustomAgent:
    now = datetime.now(UTC)
    return CustomAgent(
        id=agent_id,
        tenant_id=1,
        owner_id=10,
        name="Test Custom",
        description=None,
        system_prompt="Role-only prompt.",
        profile=AgentCapabilityProfile(
            skills=[],
            knowledge_base_ids=[1],
            platform_capabilities=[],
        ),
        tags=["should-not-leak"],
        example_questions=["Example?"],
        status="active",
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_get_agent_graph_custom_agent_builds_loaded_config(monkeypatch):
    db = MagicMock()
    service = ChatTurnService(tenant_id=1, db=db)
    domain = _custom_agent()

    captured: dict = {}

    async def fake_get_or_create(config, *, cache_revision=None, config_overrides=None):
        captured["config"] = config
        captured["cache_revision"] = cache_revision
        return MagicMock(name="compiled_graph")

    service.agent_pool.get_or_create_agent = AsyncMock(side_effect=fake_get_or_create)

    monkeypatch.setattr(
        "apps.shared.authz.ta_rbac.role_has_permission",
        AsyncMock(return_value=True),
    )

    class FakeCatalog:
        def __init__(self, *args, **kwargs):
            pass

        async def require_agent_access(self, *, agent_id, actor, action):
            assert agent_id == domain.id
            assert action == ABAC_ACTION_READ
            return domain

        def derived_tool_names(self, profile, *, assignable_skills=None):
            return ["search_documents", "load_skill"]

    monkeypatch.setattr("apps.tenant_app_service.agent_catalog.services.AgentCatalogService", FakeCatalog)
    monkeypatch.setattr(
        "apps.tenant_app_service.agent_catalog.adapters.resolve_assignable_skills",
        lambda **kwargs: [],
    )
    monkeypatch.setattr(
        "apps.tenant_app_service.agents.runtime_capability.build_agent_capability_profile",
        AsyncMock(return_value=MagicMock(allowed_tool_names=["search_documents", "load_skill"])),
    )

    user = UserDTO(
        id=10,
        username="owner@example.com",
        role="admin",
        tenant_id=1,
        tenant_name="tenant-a",
    )

    graph, profile = await service._get_agent_graph(domain.id, current_user=user)

    assert graph is not None
    assert profile is not None
    config = captured["config"]
    assert config["agent_id"] == domain.id
    assert config["name"] == domain.name
    assert config["system_prompt"] == "Role-only prompt."
    assert config["prompt_mode"] == "platform"
    assert "tags" not in config
    assert config["example_questions"] == ["Example?"]

    by_name = {item["name"]: item for item in config["default_tools"]}
    assert by_name["search_documents"]["limit"] == 5
    assert "load_skill" in by_name
