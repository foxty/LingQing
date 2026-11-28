"""LangGraph harness: max-loop finalize produces a promotable terminal AI message."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.runnables import RunnableConfig

from apps.tenant_app_service.agents.agent_base import AgentBase
from apps.tenant_app_service.chat.domain import find_promotable_final_ai_row


@pytest.fixture
def max_loop_agent(agent_stub_config_factory, runtime_context):
    stub_config = agent_stub_config_factory(
        agent_id=runtime_context.agent_id,
        agent_name=runtime_context.agent_name,
        system_prompt="test prompt",
    )
    return AgentBase(stub_config, config_overrides={"max_loop_iterations": 2})


@pytest.mark.asyncio
async def test_graph_max_loop_ends_with_promotable_text(max_loop_agent, runtime_context):
    agent = max_loop_agent

    async def noop_load(state, config=None):
        del state, config
        return {}

    async def noop_save(state, config=None):
        del state, config
        return {}

    async def stub_tool_node(state, config=None):
        del config
        last = state["messages"][-1]
        tool_calls = getattr(last, "tool_calls", None) or []
        tool_messages = [
            ToolMessage(content="stub-tool-result", tool_call_id=call["id"]) for call in tool_calls
        ]
        return {
            "messages": [*state["messages"], *tool_messages],
            "tool_call_counts": state.get("tool_call_counts", {}),
        }

    agent._load_history = noop_load
    agent._save_messages = noop_save
    agent._tool_node = stub_tool_node

    invoke_count = 0

    async def llm_side_effect(_messages, config=None, stream=False):
        del config, stream, _messages
        nonlocal invoke_count
        invoke_count += 1
        if invoke_count < 3:
            return AIMessage(
                id=str(uuid4()),
                content="",
                tool_calls=[{"name": "noop_tool", "args": {}, "id": f"call-{invoke_count}"}],
            )
        return AIMessage(id=str(uuid4()), content="Final report after max loop")

    mock_model = MagicMock()
    mock_model.ainvoke = AsyncMock(side_effect=llm_side_effect)

    graph_config = RunnableConfig(
        configurable={
            "thread_id": runtime_context.thread_id,
            "runtime": runtime_context.model_dump(),
            "session_id": runtime_context.session_id,
            "skip_load_history": True,
        }
    )

    with patch.object(agent._model_binding_manager, "get_or_create", new=AsyncMock(return_value=mock_model)):
        compiled = await agent.compile()
        result = await compiled.ainvoke(
            {
                "messages": [HumanMessage(id=str(uuid4()), content="question")],
                "loop_count": 0,
                "tool_call_counts": {},
            },
            config=graph_config,
        )

    assert invoke_count == 3
    final_ai = result["messages"][-1]
    assert isinstance(final_ai, AIMessage)
    assert final_ai.content == "Final report after max loop"
    assert not getattr(final_ai, "tool_calls", None)
    assert result["loop_count"] > agent.agent_config.max_loop_iterations

    row = SimpleNamespace(type="ai", tool_calls=getattr(final_ai, "tool_calls", None), content=final_ai.content)
    assert find_promotable_final_ai_row([row]) is row