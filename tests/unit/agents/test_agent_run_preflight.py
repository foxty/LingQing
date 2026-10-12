"""Tests for scheduled agent_run preflight."""

from unittest.mock import AsyncMock

import pytest

from apps.shared.domain.actor import ActorContext


@pytest.mark.asyncio
async def test_preflight_agent_run_only_checks_agent_invoke(monkeypatch):
    """Scheduled preflight matches chat: invoke only, not full attachment read."""
    from apps.tenant_app_service.agents.agent_run_preflight import preflight_agent_run

    require = AsyncMock(return_value=object())
    monkeypatch.setattr(
        "apps.tenant_app_service.agents.agent_run_preflight.AgentCatalogService",
        lambda tenant_id, db_session: type(
            "StubCatalog",
            (),
            {"require_agent_access": require},
        )(),
    )
    actor = ActorContext(tenant_id=1, user_id=2, user_role="member")
    await preflight_agent_run(AsyncMock(), tenant_id=1, actor=actor, agent_id=99)
    require.assert_awaited_once()
