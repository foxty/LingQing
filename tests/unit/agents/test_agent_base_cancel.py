"""Cooperative cancel checks in AgentBase."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig

from apps.tenant_app_service.agents.agent_base import AgentBase


@pytest.fixture
def agent(agent_stub_config_factory, runtime_context):
    stub_config = agent_stub_config_factory(
        agent_id=runtime_context.agent_id,
        agent_name=runtime_context.agent_name,
        system_prompt="test prompt",
    )
    return AgentBase(stub_config)


@pytest.mark.asyncio
async def test_llm_call_skips_when_run_cancelled(agent, runtime_context):
    mock_port = MagicMock()
    mock_port.is_run_cancelled = AsyncMock(return_value=True)

    config = RunnableConfig(
        configurable={
            "thread_id": runtime_context.thread_id,
            "runtime": runtime_context.model_dump(),
            "session_id": runtime_context.session_id,
            "run_id": str(uuid4()),
            "agent_run_port": mock_port,
        }
    )
    state = {
        "messages": [HumanMessage(id=str(uuid4()), content="hi")],
        "loop_count": 0,
        "tool_call_counts": {},
    }

    update = await agent._llm_call(state, config)

    assert update.get("run_cancelled") is True
    assert len(update["messages"]) == 2
    last = update["messages"][-1]
    assert not getattr(last, "tool_calls", None)


@pytest.mark.asyncio
async def test_should_continue_routes_cancelled_to_save(agent):
    state = {
        "messages": [HumanMessage(id=str(uuid4()), content="hi")],
        "loop_count": 1,
        "tool_call_counts": {},
        "run_cancelled": True,
    }
    assert agent._should_continue(state) == "save_messages"
