"""Tests for ModelBindingManager registry resolution."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.shared.llm_providers.domain import ModelProfileCategory, ResolvedModelConfig
from apps.shared.llm_providers.dtos import LLMDefaultsResponseDTO
from apps.tenant_app_service.agents.model_binding_manager import ModelBindingManager


def _resolved_config(*, profile_id: int = 7, model_id: str = "gpt-test") -> ResolvedModelConfig:
    return ResolvedModelConfig(
        profile_id=profile_id,
        profile_name="Test Profile",
        category=ModelProfileCategory.LLM,
        model_id=model_id,
        params={"max_tokens": 2048},
        provider_id=1,
        provider_display_name="Provider",
        provider_type="openai-compatible",
        provider_preset_key=None,
        api_base="https://api.example.com/v1",
        api_key="secret",
    )


def _agent_config_mock() -> MagicMock:
    config = MagicMock()
    config.agent_name = "Test Agent"
    config.temperature = None
    config.top_p = None
    config.max_tokens = None
    config.frequency_penalty = None
    return config


@pytest.mark.asyncio
async def test_get_or_create_resolves_profile_override():
    manager = ModelBindingManager(_agent_config_mock(), MagicMock())
    resolved = _resolved_config()
    bound_model = MagicMock()
    chat_model = MagicMock()
    chat_model.bind_tools.return_value = bound_model

    with (
        patch(
            "apps.tenant_app_service.agents.model_binding_manager.LLMProviderConfigService"
        ) as service_cls,
        patch(
            "apps.tenant_app_service.agents.model_binding_manager.create_chat_model",
            return_value=chat_model,
        ) as create_chat_model,
    ):
        service_cls.return_value.resolve_for_agent = AsyncMock(return_value=resolved)
        result = await manager.get_or_create(
            model_profile_id=7,
            loaded_skills=[],
            tools=[],
            tenant_id=1,
            db=AsyncMock(),
        )

    service_cls.return_value.resolve_for_agent.assert_awaited_once_with(7, mini=False)
    create_chat_model.assert_called_once_with(resolved)
    chat_model.bind_tools.assert_called_once_with([])
    assert result is bound_model
    assert manager.get_configured_model_id() == "gpt-test"
    assert manager.get_profile_label() == "Test Profile"
    assert manager.get_max_output_tokens() == 2048


@pytest.mark.asyncio
async def test_get_or_create_caches_by_profile_id():
    manager = ModelBindingManager(_agent_config_mock(), MagicMock())
    resolved = _resolved_config()
    chat_model = MagicMock()
    chat_model.bind_tools.return_value = MagicMock()

    with (
        patch(
            "apps.tenant_app_service.agents.model_binding_manager.LLMProviderConfigService"
        ) as service_cls,
        patch(
            "apps.tenant_app_service.agents.model_binding_manager.create_chat_model",
            return_value=chat_model,
        ),
    ):
        service_cls.return_value.resolve_for_agent = AsyncMock(return_value=resolved)
        first = await manager.get_or_create(
            model_profile_id=7,
            loaded_skills=[],
            tools=[],
            tenant_id=1,
            db=AsyncMock(),
        )
        second = await manager.get_or_create(
            model_profile_id=7,
            loaded_skills=[],
            tools=[],
            tenant_id=1,
            db=AsyncMock(),
        )

    assert first is second
    service_cls.return_value.resolve_for_agent.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_or_create_refreshes_when_tenant_default_changes():
    manager = ModelBindingManager(_agent_config_mock(), MagicMock())
    first_resolved = _resolved_config(profile_id=5, model_id="qwen-old")
    second_resolved = _resolved_config(profile_id=9, model_id="deepseek-new")
    chat_model = MagicMock()
    chat_model.bind_tools.side_effect = [MagicMock(name="first-bound"), MagicMock(name="second-bound")]

    defaults_responses = [
        LLMDefaultsResponseDTO(agent_profile_id=5, mini_agent_profile_id=5, embedding_profile_id=1),
        LLMDefaultsResponseDTO(agent_profile_id=9, mini_agent_profile_id=5, embedding_profile_id=1),
    ]

    with (
        patch(
            "apps.tenant_app_service.agents.model_binding_manager.LLMProviderConfigService"
        ) as service_cls,
        patch(
            "apps.tenant_app_service.agents.model_binding_manager.create_chat_model",
            return_value=chat_model,
        ) as create_chat_model,
    ):
        service_cls.return_value.get_defaults = AsyncMock(side_effect=defaults_responses)
        service_cls.return_value.resolve_for_agent = AsyncMock(side_effect=[first_resolved, second_resolved])

        first = await manager.get_or_create(
            model_profile_id=None,
            loaded_skills=[],
            tools=[],
            tenant_id=1,
            db=AsyncMock(),
        )
        second = await manager.get_or_create(
            model_profile_id=None,
            loaded_skills=[],
            tools=[],
            tenant_id=1,
            db=AsyncMock(),
        )

    assert first is not second
    assert service_cls.return_value.resolve_for_agent.await_count == 2
    assert create_chat_model.call_args_list[0].args[0].model_id == "qwen-old"
    assert create_chat_model.call_args_list[1].args[0].model_id == "deepseek-new"
    assert manager.get_configured_model_id() == "deepseek-new"


@pytest.mark.asyncio
async def test_get_or_create_scoped_by_tenant_id():
    manager = ModelBindingManager(_agent_config_mock(), MagicMock())
    tenant_one = _resolved_config(profile_id=5, model_id="tenant-one-model")
    tenant_two = _resolved_config(profile_id=5, model_id="tenant-two-model")
    chat_model = MagicMock()
    chat_model.bind_tools.side_effect = [MagicMock(name="tenant-one-bound"), MagicMock(name="tenant-two-bound")]

    with (
        patch(
            "apps.tenant_app_service.agents.model_binding_manager.LLMProviderConfigService"
        ) as service_cls,
        patch(
            "apps.tenant_app_service.agents.model_binding_manager.create_chat_model",
            return_value=chat_model,
        ),
    ):
        service_cls.return_value.get_defaults = AsyncMock(
            return_value=LLMDefaultsResponseDTO(
                agent_profile_id=5,
                mini_agent_profile_id=5,
                embedding_profile_id=1,
            )
        )
        service_cls.return_value.resolve_for_agent = AsyncMock(side_effect=[tenant_one, tenant_two])

        first = await manager.get_or_create(
            model_profile_id=None,
            loaded_skills=[],
            tools=[],
            tenant_id=1,
            db=AsyncMock(),
        )
        second = await manager.get_or_create(
            model_profile_id=None,
            loaded_skills=[],
            tools=[],
            tenant_id=2,
            db=AsyncMock(),
        )

    assert first is not second
    assert service_cls.return_value.resolve_for_agent.await_count == 2
