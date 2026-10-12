"""Runtime capability profile for chat."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from apps.shared.domain.actor import ActorContext
from apps.tenant_app_service.agents.domain import AgentCapabilityProfile
from apps.tenant_app_service.agents.runtime_capability import build_agent_capability_profile


@pytest.mark.asyncio
async def test_build_agent_capability_profile_none_for_system_agent():
    db = MagicMock()
    actor = ActorContext(tenant_id=1, user_id=1, user_role="member")
    result = await build_agent_capability_profile(db, tenant_id=1, actor=actor, agent_id=-1)
    assert result is None


@pytest.mark.asyncio
async def test_build_agent_capability_profile_without_delegate_flag(monkeypatch):
    db = MagicMock()
    actor = ActorContext(tenant_id=1, user_id=2, user_role="member")

    class FakeDomain:
        id = 5
        owner_id = 1
        profile = MagicMock(
            skills=["s1"],
            knowledge_base_ids=[1],
            data_source_ids=[2],
            api_connector_ids=[3],
        )

    async def fake_require(*_args, **_kwargs):
        return FakeDomain()

    monkeypatch.setattr(
        "apps.tenant_app_service.agents.runtime_capability.AgentCatalogService",
        lambda **kwargs: MagicMock(
            require_agent_access=AsyncMock(side_effect=fake_require),
            allowed_runtime_tool_names=MagicMock(return_value=["search_documents"]),
        ),
    )

    profile = await build_agent_capability_profile(db, tenant_id=1, actor=actor, agent_id=5)
    assert isinstance(profile, AgentCapabilityProfile)
    assert profile.allowed_collection_ids == [1]
    assert profile.allowed_data_source_ids == [2]
    assert profile.allowed_api_connector_ids == [3]
    assert not hasattr(profile, "delegate")
