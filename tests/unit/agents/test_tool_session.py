"""Unit tests for agent tool session helper."""

import pytest
from langchain_core.runnables import RunnableConfig

from apps.tenant_app_service.agents.tools.tool_session import agent_tool_db_session


class _StandaloneSessionContext:
    class _Session:
        pass

    def __init__(self):
        self.entered = False

    async def __aenter__(self):
        self.entered = True
        return self._Session()

    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.mark.asyncio
async def test_agent_tool_db_session_prefers_runtime_session():
    runtime_session = object()
    config = RunnableConfig(configurable={"db_session": runtime_session})

    async with agent_tool_db_session(config) as session:
        assert session is runtime_session


@pytest.mark.asyncio
async def test_agent_tool_db_session_falls_back_to_standalone(monkeypatch):
    standalone = _StandaloneSessionContext()
    monkeypatch.setattr(
        "apps.tenant_app_service.agents.tools.tool_session.app_db_session",
        lambda: standalone,
    )

    async with agent_tool_db_session(None) as session:
        assert isinstance(session, standalone._Session)
    assert standalone.entered is True
