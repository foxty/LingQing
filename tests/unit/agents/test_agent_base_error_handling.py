"""Tests for AgentBase error handling in _llm_call.

Verifies that when the LLM call fails:
1. An error AIMessage is returned as the response (no exception raised)
2. The graph continues normally to _should_continue → save_messages
3. Original messages are preserved alongside the error
"""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableConfig

from apps.tenant_app_service.agents.agent_base import AgentBase
from apps.tenant_app_service.agents.domain import PromptContextStats


@pytest.fixture
def agent(agent_stub_config_factory, runtime_context):
    stub_config = agent_stub_config_factory(
        agent_id=runtime_context.agent_id,
        agent_name=runtime_context.agent_name,
        system_prompt="test prompt",
    )
    return AgentBase(stub_config)


@pytest.fixture
def base_state():
    return {
        "messages": [HumanMessage(id=str(uuid4()), content="hello")],
        "loop_count": 0,
        "tool_call_counts": {},
    }


@pytest.fixture
def config(runtime_context):
    return RunnableConfig(
        configurable={
            "thread_id": runtime_context.thread_id,
            "runtime": runtime_context.model_dump(),
            "session_id": runtime_context.session_id,
        }
    )


@pytest.mark.asyncio
class TestLlmCallErrorHandling:
    async def test_llm_error_returns_error_ai_message(self, agent, base_state, config):
        """When LLM raises, _llm_call returns normally with an error AIMessage."""
        mock_model = MagicMock()
        mock_model.ainvoke = AsyncMock(side_effect=RuntimeError("model overloaded"))

        with patch.object(
            agent._model_binding_manager, "get_or_create", new=AsyncMock(return_value=mock_model)
        ):
            state_update = await agent._llm_call(base_state, config)

        last_msg = state_update["messages"][-1]
        assert isinstance(last_msg, AIMessage)
        assert "model overloaded" in last_msg.content
        assert last_msg.additional_kwargs.get("error") is True

    async def test_llm_error_does_not_raise(self, agent, base_state, config):
        """_llm_call does not propagate the LLM exception — the graph flow continues."""
        mock_model = MagicMock()
        mock_model.ainvoke = AsyncMock(side_effect=ValueError("bad request"))

        with patch.object(
            agent._model_binding_manager, "get_or_create", new=AsyncMock(return_value=mock_model)
        ):
            state_update = await agent._llm_call(base_state, config)

        assert "messages" in state_update
        assert state_update["loop_count"] == 1

    async def test_llm_error_preserves_original_messages(self, agent, base_state, config):
        """The original user message is preserved alongside the error AIMessage."""
        mock_model = MagicMock()
        mock_model.ainvoke = AsyncMock(side_effect=ValueError("bad request"))

        with patch.object(
            agent._model_binding_manager, "get_or_create", new=AsyncMock(return_value=mock_model)
        ):
            state_update = await agent._llm_call(base_state, config)

        msgs = state_update["messages"]
        assert any(isinstance(m, HumanMessage) and m.content == "hello" for m in msgs)
        assert isinstance(msgs[-1], AIMessage)

    async def test_llm_error_response_has_no_tool_calls(self, agent, base_state, config):
        """Error AIMessage has no tool_calls so _should_continue routes to save_messages."""
        mock_model = MagicMock()
        mock_model.ainvoke = AsyncMock(side_effect=RuntimeError("timeout"))

        with patch.object(
            agent._model_binding_manager, "get_or_create", new=AsyncMock(return_value=mock_model)
        ):
            state_update = await agent._llm_call(base_state, config)

        error_msg = state_update["messages"][-1]
        assert not getattr(error_msg, "tool_calls", None)

        route = agent._should_continue(state_update)
        assert route == "save_messages"

    async def test_llm_call_passes_prompt_context_stats_to_tracker(self, agent, base_state, config):
        """_llm_call should pass PromptContextStats into llm_call_tracker."""
        mock_model = MagicMock()
        mock_model.ainvoke = AsyncMock(return_value=AIMessage(id=str(uuid4()), content="ok"))
        captured: dict[str, object] = {}

        @asynccontextmanager
        async def fake_llm_call_tracker(
            model_key,
            runtime,
            prompt_context_stats=None,
            configured_model_id=None,
            max_output_tokens=None,
        ):
            captured["model_key"] = model_key
            captured["stats"] = prompt_context_stats
            captured["max_output_tokens"] = max_output_tokens

            class _Tracker:
                def record_response(self, response):
                    return response

            yield _Tracker()

        with (
            patch.object(
                agent._model_binding_manager, "get_or_create", new=AsyncMock(return_value=mock_model)
            ),
            patch.object(
                agent._model_binding_manager,
                "get_configured_model_id",
                return_value="test-model",
            ),
            patch("apps.tenant_app_service.agents.agent_base.llm_call_tracker", fake_llm_call_tracker),
        ):
            await agent._llm_call(base_state, config)

        assert captured["model_key"] == "test-model"
        stats = captured["stats"]
        assert isinstance(stats, PromptContextStats)
        assert stats.final_count > 0
        mock_model.ainvoke.assert_awaited()
        assert mock_model.ainvoke.await_args.kwargs.get("stream") is False
