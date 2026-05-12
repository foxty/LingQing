"""Unit tests for MiniAgentExecutor core functionality."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage
from pydantic import BaseModel

from apps.tenant_app_service.agents.domain import (
    AgentRuntimeContext,
    AgentTenantContext,
    AgentUserContext,
)
from apps.tenant_app_service.agents.mini.domain import MiniAgentConfig
from apps.tenant_app_service.agents.mini.executor import MiniAgentExecutor


def _make_tenant_config(model_name: str = "test-model") -> dict:
    """Create tenant config with mini_agent_model configured."""
    return {
        "mini_agent_model": {
            "name": "Test Model",
            "type": "openai-compatible",
            "api_base": "https://api.test.com/v1",
            "api_key": "test-api-key",
            "model_id": model_name,
            "params": {"temperature": 0.1},
        }
    }


def _make_runtime_context(tenant_config: dict | None = None) -> AgentRuntimeContext:
    """Create a runtime context with tenant config."""
    return AgentRuntimeContext(
        tenant=AgentTenantContext(
            tenant_id=1,
            tenant_name="test_tenant",
            config=tenant_config or _make_tenant_config(),
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


def _make_mock_model(return_value, side_effect=None):
    """Create a mock model with configurable behavior."""
    mock_model = AsyncMock()
    if side_effect:
        mock_model.ainvoke = AsyncMock(side_effect=side_effect)
    else:
        mock_model.ainvoke = AsyncMock(return_value=return_value)
    mock_model.with_structured_output = MagicMock(return_value=mock_model)
    return mock_model


@pytest.mark.asyncio
class TestMiniAgentExecutor:
    """Test MiniAgentExecutor core functionality."""

    async def test_execute_simple_text_response(self):
        """Test executing a simple text LLM call."""
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
            model_key="test-model",
            temperature=0.7,
        )

        with patch(
            "apps.tenant_app_service.agents.mini.executor.LLMModelFactory"
        ) as mock_factory_cls:
            mock_factory = MagicMock()
            mock_factory.is_configured.return_value = True
            mock_factory.get_model_name.return_value = "test-model"
            mock_factory.get_mini_agent_model.return_value = mock_model
            mock_factory_cls.return_value = mock_factory

            mock_db = AsyncMock()
            executor = MiniAgentExecutor(mock_db)
            context = _make_runtime_context()

            result = await executor.execute(
                config=config,
                context=context,
                user_prompt="Summarize: test text",
            )

            assert result.content == "Summary of text"

    async def test_execute_structured_response(self):
        """Test executing with structured output."""

        class OutputModel(BaseModel):
            category: str
            confidence: float

        mock_output = OutputModel(category="urgent", confidence=0.95)
        mock_model = _make_mock_model(return_value=mock_output)

        config = MiniAgentConfig(
            agent_id=1,
            agent_name="Test Mini Agent",
            system_prompt="You are a classifier.",
            model_key="test-model",
            temperature=0.2,
            response_format=OutputModel,
        )

        with patch(
            "apps.tenant_app_service.agents.mini.executor.LLMModelFactory"
        ) as mock_factory_cls:
            mock_factory = MagicMock()
            mock_factory.is_configured.return_value = True
            mock_factory.get_model_name.return_value = "test-model"
            mock_factory.get_mini_agent_model.return_value = mock_model
            mock_factory_cls.return_value = mock_factory

            mock_db = AsyncMock()
            executor = MiniAgentExecutor(mock_db)
            context = _make_runtime_context()

            result = await executor.execute(
                config=config,
                context=context,
                user_prompt="Classify this",
            )

            assert result.structured_data is not None
            assert result.structured_data["category"] == "urgent"
            assert result.structured_data["confidence"] == 0.95

    async def test_execute_with_retry_on_transient_error(self):
        """Test executor retries on transient errors."""
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
            model_key="test-model",
        )

        with patch(
            "apps.tenant_app_service.agents.mini.executor.LLMModelFactory"
        ) as mock_factory_cls:
            mock_factory = MagicMock()
            mock_factory.is_configured.return_value = True
            mock_factory.get_model_name.return_value = "test-model"
            mock_factory.get_mini_agent_model.return_value = mock_model
            mock_factory_cls.return_value = mock_factory

            mock_db = AsyncMock()
            executor = MiniAgentExecutor(mock_db)
            context = _make_runtime_context()

            with patch("asyncio.sleep", new_callable=AsyncMock):
                result = await executor.execute(
                    config=config,
                    context=context,
                    user_prompt="Test",
                )

            assert result.content == "Success"
            assert mock_model.ainvoke.call_count == 2

    async def test_execute_failure_after_max_retries(self):
        """Test executor fails after max retries exceeded."""
        mock_model = _make_mock_model(
            return_value=None,
            side_effect=Exception("429 Rate limit"),
        )

        config = MiniAgentConfig(
            agent_id=1,
            agent_name="Test Mini Agent",
            system_prompt="You are a helpful assistant.",
            model_key="test-model",
        )

        with patch(
            "apps.tenant_app_service.agents.mini.executor.LLMModelFactory"
        ) as mock_factory_cls:
            mock_factory = MagicMock()
            mock_factory.is_configured.return_value = True
            mock_factory.get_model_name.return_value = "test-model"
            mock_factory.get_mini_agent_model.return_value = mock_model
            mock_factory_cls.return_value = mock_factory

            mock_db = AsyncMock()
            executor = MiniAgentExecutor(mock_db)
            context = _make_runtime_context()

            with patch("asyncio.sleep", new_callable=AsyncMock):
                with pytest.raises(Exception) as excinfo:
                    await executor.execute(
                        config=config,
                        context=context,
                        user_prompt="Test",
                    )

            assert "Rate limit" in str(excinfo.value)
            assert mock_model.ainvoke.call_count == 3

    async def test_execute_non_transient_error_no_retry(self):
        """Test executor doesn't retry on non-transient errors."""
        mock_model = _make_mock_model(
            return_value=None,
            side_effect=ValueError("Invalid API key"),
        )

        config = MiniAgentConfig(
            agent_id=1,
            agent_name="Test Mini Agent",
            system_prompt="You are a helpful assistant.",
            model_key="test-model",
        )

        with patch(
            "apps.tenant_app_service.agents.mini.executor.LLMModelFactory"
        ) as mock_factory_cls:
            mock_factory = MagicMock()
            mock_factory.is_configured.return_value = True
            mock_factory.get_model_name.return_value = "test-model"
            mock_factory.get_mini_agent_model.return_value = mock_model
            mock_factory_cls.return_value = mock_factory

            mock_db = AsyncMock()
            executor = MiniAgentExecutor(mock_db)
            context = _make_runtime_context()

            with pytest.raises(ValueError) as excinfo:
                await executor.execute(
                    config=config,
                    context=context,
                    user_prompt="Test",
                )

            assert "Invalid API key" in str(excinfo.value)
            assert mock_model.ainvoke.call_count == 1

    async def test_is_transient_error(self):
        """Test transient error detection."""
        mock_db = AsyncMock()
        executor = MiniAgentExecutor(mock_db)

        # Transient errors
        assert executor._is_transient_error(Exception("429 Too many requests"))
        assert executor._is_transient_error(Exception("503 Service unavailable"))
        assert executor._is_transient_error(Exception("504 Gateway timeout"))
        assert executor._is_transient_error(Exception("timeout"))
        assert executor._is_transient_error(Exception("rate limit exceeded"))

        # Non-transient errors
        assert not executor._is_transient_error(ValueError("Invalid input"))
        assert not executor._is_transient_error(Exception("API key not found"))
        assert not executor._is_transient_error(Exception("Permission denied"))
