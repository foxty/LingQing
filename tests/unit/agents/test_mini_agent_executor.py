"""Unit tests for MiniAgentExecutor core functionality."""

from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage
from pydantic import BaseModel

from apps.shared.llm_providers.domain import ModelProfileCategory, ResolvedModelConfig
from apps.tenant_app_service.agents.domain import (
    AgentRuntimeContext,
    AgentTenantContext,
    AgentUserContext,
)
from apps.tenant_app_service.agents.mini.domain import MiniAgentConfig
from apps.tenant_app_service.agents.mini.executor import MiniAgentExecutor


def _make_runtime_context() -> AgentRuntimeContext:
    return AgentRuntimeContext(
        tenant=AgentTenantContext(
            tenant_id=1,
            tenant_name="test_tenant",
            config={},
        ),
        user=AgentUserContext(
            user_id=100,
            username="test_user",
            role="user",
            tenant_id=1,
            tenant_name="test_tenant",
        ),
        agent_id=10,
        agent_name="test_agent",
        thread_id="test-thread",
        session_id="test-session",
    )


def _resolved_config(model_id: str = "test-model") -> ResolvedModelConfig:
    return ResolvedModelConfig(
        profile_id=1,
        profile_name="test-model",
        category=ModelProfileCategory.LLM,
        model_id=model_id,
        params={"temperature": 0.1},
        provider_id=1,
        provider_display_name="Test Provider",
        provider_type="openai-compatible",
        provider_preset_key=None,
        api_base="https://api.test.com/v1",
        api_key="test-api-key",
    )


def _make_mock_model(return_value, side_effect=None):
    mock_model = AsyncMock()
    if side_effect:
        mock_model.ainvoke = AsyncMock(side_effect=side_effect)
    else:
        mock_model.ainvoke = AsyncMock(return_value=return_value)
    mock_model.with_structured_output = MagicMock(return_value=mock_model)
    return mock_model


@contextmanager
def _registry_patches(mock_model):
    service = MagicMock()
    service.resolve_default_llm_profile = AsyncMock(return_value=_resolved_config())
    with (
        patch(
            "apps.tenant_app_service.agents.mini.executor.LLMProviderConfigService",
            return_value=service,
        ),
        patch(
            "apps.tenant_app_service.agents.mini.executor.create_chat_model",
            return_value=mock_model,
        ),
    ):
        yield


@pytest.mark.asyncio
class TestMiniAgentExecutor:
    async def test_execute_simple_text_response(self):
        mock_model = _make_mock_model(
            return_value=AIMessage(
                content="Summary of text",
                usage_metadata={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
            )
        )
        config = MiniAgentConfig(
            agent_id=1,
            agent_name="Test Mini Agent",
            system_prompt="You are a helpful assistant.",
            temperature=0.7,
        )

        with _registry_patches(mock_model):
            executor = MiniAgentExecutor(AsyncMock())
            result = await executor.execute(
                config=config,
                context=_make_runtime_context(),
                user_prompt="Summarize: test text",
            )

        assert result.content == "Summary of text"

    async def test_execute_structured_response(self):
        class OutputModel(BaseModel):
            category: str
            confidence: float

        mock_output = OutputModel(category="urgent", confidence=0.95)
        mock_model = _make_mock_model(return_value=mock_output)
        config = MiniAgentConfig(
            agent_id=1,
            agent_name="Test Mini Agent",
            system_prompt="You are a classifier.",
            temperature=0.2,
            response_format=OutputModel,
        )

        with _registry_patches(mock_model):
            executor = MiniAgentExecutor(AsyncMock())
            result = await executor.execute(
                config=config,
                context=_make_runtime_context(),
                user_prompt="Classify this",
            )

        assert result.structured_data is not None
        assert result.structured_data["category"] == "urgent"
        assert result.structured_data["confidence"] == 0.95

    async def test_execute_with_retry_on_transient_error(self):
        mock_model = _make_mock_model(
            return_value=None,
            side_effect=[
                Exception("429 Rate limit exceeded"),
                AIMessage(
                    content="Success",
                    usage_metadata={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
                ),
            ],
        )
        config = MiniAgentConfig(
            agent_id=1,
            agent_name="Test Mini Agent",
            system_prompt="You are a helpful assistant.",
        )

        with _registry_patches(mock_model):
            executor = MiniAgentExecutor(AsyncMock())
            with patch("asyncio.sleep", new_callable=AsyncMock):
                result = await executor.execute(
                    config=config,
                    context=_make_runtime_context(),
                    user_prompt="Test",
                )

        assert result.content == "Success"
        assert mock_model.ainvoke.call_count == 2

    async def test_execute_failure_after_max_retries(self):
        mock_model = _make_mock_model(return_value=None, side_effect=Exception("429 Rate limit"))
        config = MiniAgentConfig(
            agent_id=1,
            agent_name="Test Mini Agent",
            system_prompt="You are a helpful assistant.",
        )

        with _registry_patches(mock_model):
            executor = MiniAgentExecutor(AsyncMock())
            with patch("asyncio.sleep", new_callable=AsyncMock):
                with pytest.raises(Exception) as excinfo:
                    await executor.execute(
                        config=config,
                        context=_make_runtime_context(),
                        user_prompt="Test",
                    )

        assert "Rate limit" in str(excinfo.value)
        assert mock_model.ainvoke.call_count == 3

    async def test_execute_non_transient_error_no_retry(self):
        mock_model = _make_mock_model(return_value=None, side_effect=ValueError("Invalid API key"))
        config = MiniAgentConfig(
            agent_id=1,
            agent_name="Test Mini Agent",
            system_prompt="You are a helpful assistant.",
        )

        with _registry_patches(mock_model):
            executor = MiniAgentExecutor(AsyncMock())
            with pytest.raises(ValueError) as excinfo:
                await executor.execute(
                    config=config,
                    context=_make_runtime_context(),
                    user_prompt="Test",
                )

        assert "Invalid API key" in str(excinfo.value)
        assert mock_model.ainvoke.call_count == 1

    async def test_is_transient_error(self):
        executor = MiniAgentExecutor(AsyncMock())
        assert executor._is_transient_error(Exception("429 Too many requests"))
        assert executor._is_transient_error(Exception("503 Service unavailable"))
        assert executor._is_transient_error(Exception("504 Gateway timeout"))
        assert executor._is_transient_error(Exception("timeout"))
        assert executor._is_transient_error(Exception("rate limit exceeded"))
        assert not executor._is_transient_error(ValueError("Invalid input"))
        assert not executor._is_transient_error(Exception("API key not found"))
        assert not executor._is_transient_error(Exception("Permission denied"))
