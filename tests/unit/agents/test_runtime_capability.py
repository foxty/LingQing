"""Runtime capability profile for chat and delegated collection reads."""

from unittest.mock import AsyncMock

import pytest

from apps.shared.domain.actor import ActorContext
from apps.tenant_app_service.agents.context import delegated_collection_ids
from apps.tenant_app_service.agents.domain import AgentCapabilityProfile
from apps.shared.core.exceptions import ResourceNotFoundError
from apps.tenant_app_service.agents.runtime_capability import (
    build_agent_capability_profile,
    resolve_delegated_collection_ids,
)


def test_delegated_collection_ids_helper():
    profile = AgentCapabilityProfile(
        allowed_collection_ids=[1, 2],
        delegate=True,
    )
    assert delegated_collection_ids(profile) == [1, 2]
    assert delegated_collection_ids(AgentCapabilityProfile(delegate=False, allowed_collection_ids=[1])) is None


@pytest.mark.asyncio
async def test_build_agent_capability_profile_none_for_system_agent():
    db = AsyncMock()
    actor = ActorContext(tenant_id=1, user_id=2, user_role="member")
    result = await build_agent_capability_profile(db, tenant_id=1, actor=actor, agent_id=-1)
    assert result is None


@pytest.mark.asyncio
async def test_resolve_delegated_collection_ids_uses_profile(monkeypatch):
    db = AsyncMock()
    actor = ActorContext(tenant_id=1, user_id=2, user_role="member")
    profile = AgentCapabilityProfile(allowed_collection_ids=[7], delegate=True)

    monkeypatch.setattr(
        "apps.tenant_app_service.agents.runtime_capability.build_agent_capability_profile",
        AsyncMock(return_value=profile),
    )

    result = await resolve_delegated_collection_ids(db, tenant_id=1, actor=actor, agent_id=5)
    assert result == [7]


@pytest.mark.asyncio
async def test_resolve_delegated_collection_ids_missing_agent_returns_none(monkeypatch):
    db = AsyncMock()
    actor = ActorContext(tenant_id=1, user_id=2, user_role="member")

    async def raise_not_found(*_args, **_kwargs):
        raise ResourceNotFoundError("Agent 1 not found")

    monkeypatch.setattr(
        "apps.tenant_app_service.agents.runtime_capability.build_agent_capability_profile",
        raise_not_found,
    )

    result = await resolve_delegated_collection_ids(db, tenant_id=1, actor=actor, agent_id=1)
    assert result is None
