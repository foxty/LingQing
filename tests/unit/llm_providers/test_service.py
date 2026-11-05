"""Tests for shared LLMProviderConfigService."""

import pytest

from apps.shared.core.exceptions import ValidationError
from apps.shared.db.models import Tenant
from apps.shared.llm_providers.domain import ModelProfileCategory
from apps.shared.llm_providers.dtos import (
    CreateLLMModelProfileRequest,
    CreateLLMProviderRequest,
    UpdateLLMDefaultsRequest,
    UpdateLLMModelProfileRequest,
    UpdateLLMProviderRequest,
)
from apps.shared.llm_providers.service import LLMProviderConfigService
from apps.shared.utils.field_cipher import FieldCipher

pytestmark = pytest.mark.asyncio


async def _seed_tenant(async_db_session) -> Tenant:
    tenant = Tenant(name="service-tenant", slug="service-tenant", status="active", config={})
    async_db_session.add(tenant)
    await async_db_session.flush()
    await async_db_session.refresh(tenant)
    return tenant


async def test_create_provider_and_profile(async_db_session):
    tenant = await _seed_tenant(async_db_session)
    service = LLMProviderConfigService(tenant.id, async_db_session)

    provider = await service.create_provider(
        CreateLLMProviderRequest(
            display_name="Deepseek Prod",
            preset_key="deepseek",
            api_base="https://api.deepseek.com",
            api_key="secret-key",
        )
    )
    profile = await service.create_profile(
        CreateLLMModelProfileRequest(
            provider_id=provider.id,
            name="Reasoning",
            category=ModelProfileCategory.LLM,
            model_id="deepseek-v4-pro",
            catalog_model_key="deepseek/deepseek-v4-pro",
        )
    )

    providers = await service.list_providers()
    profiles = await service.list_profiles(category=ModelProfileCategory.LLM)

    assert len(providers) == 1
    assert len(profiles) == 1
    assert profiles[0].id == profile.id
    assert provider.api_key_masked
    assert provider.api_key_masked != "secret-key"


async def test_delete_provider_blocked_when_profiles_exist(async_db_session):
    tenant = await _seed_tenant(async_db_session)
    service = LLMProviderConfigService(tenant.id, async_db_session)

    provider = await service.create_provider(
        CreateLLMProviderRequest(
            display_name="Provider",
            api_base="https://api.example.com/v1",
            api_key="secret-key",
        )
    )
    await service.create_profile(
        CreateLLMModelProfileRequest(
            provider_id=provider.id,
            name="Model",
            category=ModelProfileCategory.LLM,
            model_id="gpt-test",
        )
    )

    with pytest.raises(ValidationError, match="Cannot delete provider"):
        await service.delete_provider(provider.id)


async def test_resolve_profile(async_db_session):
    tenant = await _seed_tenant(async_db_session)
    service = LLMProviderConfigService(tenant.id, async_db_session)
    cipher = FieldCipher()

    provider = await service.create_provider(
        CreateLLMProviderRequest(
            display_name="Provider",
            api_base="https://api.example.com/v1",
            api_key="plain-secret",
        )
    )
    profile = await service.create_profile(
        CreateLLMModelProfileRequest(
            provider_id=provider.id,
            name="Model",
            category=ModelProfileCategory.LLM,
            model_id="gpt-test",
            params={"temperature": 0.2},
        )
    )

    resolved = await service.resolve_profile(profile.id)
    assert resolved.model_id == "gpt-test"
    assert resolved.api_key == "plain-secret"
    assert resolved.params == {"temperature": 0.2}
    assert cipher.mask_value(resolved.api_key) == provider.api_key_masked


async def test_test_provider_connection_uses_linked_profile(async_db_session):
    tenant = await _seed_tenant(async_db_session)
    service = LLMProviderConfigService(tenant.id, async_db_session)

    provider = await service.create_provider(
        CreateLLMProviderRequest(
            display_name="Provider",
            preset_key="deepseek",
            api_base="https://api.deepseek.com",
            api_key="plain-secret",
        )
    )
    profile = await service.create_profile(
        CreateLLMModelProfileRequest(
            provider_id=provider.id,
            name="Reasoning",
            category=ModelProfileCategory.LLM,
            model_id="deepseek-v4-pro",
        )
    )

    async def fake_test_resolved(resolved):
        assert resolved.model_id == "deepseek-v4-pro"
        assert resolved.api_base == "https://api.deepseek.com"
        return "Connection test passed"

    service._test_resolved_connection = fake_test_resolved  # type: ignore[method-assign]
    message = await service.test_provider_connection(provider.id)
    assert message == "Connection test passed"
    assert profile.id is not None


async def test_test_provider_connection_requires_profile_or_catalog_model(async_db_session):
    tenant = await _seed_tenant(async_db_session)
    service = LLMProviderConfigService(tenant.id, async_db_session)

    provider = await service.create_provider(
        CreateLLMProviderRequest(
            display_name="Custom Provider",
            api_base="https://api.example.com/v1",
            api_key="plain-secret",
        )
    )

    with pytest.raises(ValidationError, match="Create a model profile first"):
        await service.test_provider_connection(provider.id)


async def test_test_profile_connection_uses_profile_runtime_snapshot(async_db_session, monkeypatch):
    tenant = await _seed_tenant(async_db_session)
    service = LLMProviderConfigService(tenant.id, async_db_session)

    provider = await service.create_provider(
        CreateLLMProviderRequest(
            display_name="Provider",
            api_base="https://api.example.com/v1",
            api_key="plain-secret",
        )
    )
    profile = await service.create_profile(
        CreateLLMModelProfileRequest(
            provider_id=provider.id,
            name="Reasoning",
            category=ModelProfileCategory.LLM,
            model_id="test-model",
            params={"temperature": 0.33, "max_tokens": 512},
            reasoning_config={
                "supports_thinking": True,
                "thinking_effort_options": [
                    {"name": "low", "value": "low"},
                    {"name": "max", "value": "max"},
                ],
                "default_thinking_effort": "max",
            },
        )
    )

    captured: list = []

    def fake_create_chat_model(resolved, *, thinking_effort=None):
        captured.append(resolved)
        assert thinking_effort is None

        class _Model:
            async def ainvoke(self, _msg):
                return "ok"

        return _Model()

    monkeypatch.setattr(
        "apps.shared.llm_providers.service.create_chat_model",
        fake_create_chat_model,
    )

    message = await service.test_profile_connection(profile.id)
    assert message == "Connection test passed"
    assert len(captured) == 1
    resolved = captured[0]
    assert resolved.model_id == "test-model"
    assert resolved.params == {"temperature": 0.33, "max_tokens": 512}
    assert resolved.reasoning_config is not None
    assert resolved.reasoning_config.get("default_thinking_effort") == "max"


async def test_create_and_update_profile_persist_default_thinking_effort(async_db_session):
    tenant = await _seed_tenant(async_db_session)
    service = LLMProviderConfigService(tenant.id, async_db_session)

    provider = await service.create_provider(
        CreateLLMProviderRequest(
            display_name="Provider",
            api_base="https://api.example.com/v1",
            api_key="plain-secret",
        )
    )
    profile = await service.create_profile(
        CreateLLMModelProfileRequest(
            provider_id=provider.id,
            name="Reasoning",
            category=ModelProfileCategory.LLM,
            model_id="test-model",
            reasoning_config={
                "supports_thinking": True,
                "thinking_effort_options": [
                    {"name": "low", "value": "low"},
                    {"name": "max", "value": "max"},
                ],
                "default_thinking_effort": "max",
            },
        )
    )

    resolved = await service.resolve_profile(profile.id)
    assert resolved.reasoning_config is not None
    assert resolved.reasoning_config.get("default_thinking_effort") == "max"

    await service.update_profile(
        profile.id,
        UpdateLLMModelProfileRequest(
            reasoning_config={
                "supports_thinking": True,
                "thinking_effort_options": [
                    {"name": "low", "value": "low"},
                    {"name": "high", "value": "high"},
                ],
                "default_thinking_effort": "high",
            },
        ),
    )
    updated = await service.resolve_profile(profile.id)
    assert updated.reasoning_config is not None
    assert updated.reasoning_config.get("default_thinking_effort") == "high"


async def test_test_profile_connection_applies_runtime_params_and_default_thinking(
    async_db_session,
    monkeypatch,
):
    tenant = await _seed_tenant(async_db_session)
    service = LLMProviderConfigService(tenant.id, async_db_session)

    provider = await service.create_provider(
        CreateLLMProviderRequest(
            display_name="DBX",
            preset_key="databricks-ai-gateway",
            api_base="https://workspace.example.com/ai-gateway/mlflow/v1",
            api_key="plain-secret",
        )
    )
    profile = await service.create_profile(
        CreateLLMModelProfileRequest(
            provider_id=provider.id,
            name="GLM",
            category=ModelProfileCategory.LLM,
            model_id="system.ai.glm-5-3",
            params={"temperature": 0.33, "max_tokens": 512, "top_p": 0.9},
            reasoning_config={
                "supports_thinking": True,
                "thinking_effort_options": [
                    {"name": "low", "value": "low"},
                    {"name": "max", "value": "max"},
                ],
                "default_thinking_effort": "max",
            },
        )
    )

    captured: list[dict] = []

    def fake_create_openai_compatible_chat_model(**kwargs):
        captured.append(kwargs)

        class _Model:
            async def ainvoke(self, _msg):
                return "ok"

        return _Model()

    monkeypatch.setattr(
        "apps.shared.infra.llm.llm_model_resolver._create_openai_compatible_chat_model",
        fake_create_openai_compatible_chat_model,
    )

    message = await service.test_profile_connection(profile.id)
    assert message == "Connection test passed"
    assert len(captured) == 1
    wire = captured[0]
    assert wire["thinking_effort"] == "max"
    assert wire["temperature"] == 0.33
    assert wire["max_tokens"] == 512
    assert wire["top_p"] == 0.9
    assert wire["resolved"].provider_config == {"thinking_request_mode": "reasoning_effort"}


async def test_test_profile_connection_embedding_uses_resolved_profile(async_db_session, monkeypatch):
    tenant = await _seed_tenant(async_db_session)
    service = LLMProviderConfigService(tenant.id, async_db_session)

    provider = await service.create_provider(
        CreateLLMProviderRequest(
            display_name="Provider",
            api_base="https://api.example.com/v1",
            embedding_api_base="https://api.example.com/v1",
            api_key="plain-secret",
        )
    )
    profile = await service.create_profile(
        CreateLLMModelProfileRequest(
            provider_id=provider.id,
            name="Embed",
            category=ModelProfileCategory.EMBEDDING,
            model_id="text-embedding-test",
        )
    )

    captured: list = []

    class _Embeddings:
        async def aembed_query(self, text: str):
            captured.append(text)
            return [0.1, 0.2]

    def fake_create_embeddings(resolved):
        captured.append(resolved)
        return _Embeddings()

    monkeypatch.setattr(
        "apps.shared.llm_providers.service.create_embeddings",
        fake_create_embeddings,
    )

    message = await service.test_profile_connection(profile.id)
    assert message == "Connection test passed"
    assert len(captured) == 2
    resolved = captured[0]
    assert resolved.model_id == "text-embedding-test"
    assert resolved.api_base == "https://api.example.com/v1"
    assert captured[1] == "Hello, this is a connection test."


async def test_test_provider_connection_routes_through_profile_resolution(async_db_session, monkeypatch):
    tenant = await _seed_tenant(async_db_session)
    service = LLMProviderConfigService(tenant.id, async_db_session)

    provider = await service.create_provider(
        CreateLLMProviderRequest(
            display_name="Provider",
            api_base="https://api.example.com/v1",
            api_key="plain-secret",
        )
    )
    profile = await service.create_profile(
        CreateLLMModelProfileRequest(
            provider_id=provider.id,
            name="Primary",
            category=ModelProfileCategory.LLM,
            model_id="primary-model",
            params={"temperature": 0.5},
        )
    )
    await service.create_profile(
        CreateLLMModelProfileRequest(
            provider_id=provider.id,
            name="Secondary",
            category=ModelProfileCategory.LLM,
            model_id="secondary-model",
        )
    )

    seen_profile_ids: list[int] = []

    async def fake_test_profile_connection(profile_id: int, api_key: str = "") -> str:
        seen_profile_ids.append(profile_id)
        resolved = await service.resolve_profile(profile_id)
        assert resolved.model_id == "primary-model"
        assert resolved.params == {"temperature": 0.5}
        return "Connection test passed"

    monkeypatch.setattr(service, "test_profile_connection", fake_test_profile_connection)

    message = await service.test_provider_connection(provider.id)
    assert message == "Connection test passed"
    assert seen_profile_ids == [profile.id]


async def test_resolve_for_agent_uses_override_profile(async_db_session):
    tenant = await _seed_tenant(async_db_session)
    service = LLMProviderConfigService(tenant.id, async_db_session)

    provider = await service.create_provider(
        CreateLLMProviderRequest(
            display_name="Provider",
            api_base="https://api.example.com/v1",
            api_key="plain-secret",
        )
    )
    override = await service.create_profile(
        CreateLLMModelProfileRequest(
            provider_id=provider.id,
            name="Override",
            category=ModelProfileCategory.LLM,
            model_id="override-model",
        )
    )
    default = await service.create_profile(
        CreateLLMModelProfileRequest(
            provider_id=provider.id,
            name="Default",
            category=ModelProfileCategory.LLM,
            model_id="default-model",
        )
    )
    await service.update_defaults(UpdateLLMDefaultsRequest(agent_profile_id=default.id))

    resolved = await service.resolve_for_agent(override.id)
    assert resolved.model_id == "override-model"
    assert resolved.profile_id == override.id


async def test_resolve_for_agent_falls_back_to_tenant_default(async_db_session):
    tenant = await _seed_tenant(async_db_session)
    service = LLMProviderConfigService(tenant.id, async_db_session)

    provider = await service.create_provider(
        CreateLLMProviderRequest(
            display_name="Provider",
            api_base="https://api.example.com/v1",
            api_key="plain-secret",
        )
    )
    default = await service.create_profile(
        CreateLLMModelProfileRequest(
            provider_id=provider.id,
            name="Default",
            category=ModelProfileCategory.LLM,
            model_id="tenant-default-model",
        )
    )
    await service.update_defaults(UpdateLLMDefaultsRequest(agent_profile_id=default.id))

    resolved = await service.resolve_for_agent(None)
    assert resolved.model_id == "tenant-default-model"
    assert resolved.profile_id == default.id


async def test_resolve_for_agent_rejects_embedding_profile(async_db_session):
    tenant = await _seed_tenant(async_db_session)
    service = LLMProviderConfigService(tenant.id, async_db_session)

    provider = await service.create_provider(
        CreateLLMProviderRequest(
            display_name="Provider",
            api_base="https://api.example.com/v1",
            api_key="plain-secret",
        )
    )
    embedding = await service.create_profile(
        CreateLLMModelProfileRequest(
            provider_id=provider.id,
            name="Embedding",
            category=ModelProfileCategory.EMBEDDING,
            model_id="text-embedding-test",
        )
    )

    with pytest.raises(ValidationError, match="category 'llm'"):
        await service.resolve_for_agent(embedding.id)


async def test_resolve_profile_rejects_disabled_provider(async_db_session):
    tenant = await _seed_tenant(async_db_session)
    service = LLMProviderConfigService(tenant.id, async_db_session)

    provider = await service.create_provider(
        CreateLLMProviderRequest(
            display_name="Provider",
            api_base="https://api.example.com/v1",
            api_key="plain-secret",
        )
    )
    profile = await service.create_profile(
        CreateLLMModelProfileRequest(
            provider_id=provider.id,
            name="Model",
            category=ModelProfileCategory.LLM,
            model_id="gpt-test",
        )
    )
    await service.update_provider(
        provider.id,
        UpdateLLMProviderRequest(status="disabled"),
    )

    with pytest.raises(ValidationError, match="disabled"):
        await service.resolve_profile(profile.id)


async def test_create_profile_seeds_runtime_snapshots_from_catalog(async_db_session):
    tenant = await _seed_tenant(async_db_session)
    service = LLMProviderConfigService(tenant.id, async_db_session)

    provider = await service.create_provider(
        CreateLLMProviderRequest(
            display_name="Bailian",
            preset_key="bailian",
            api_base="https://dashscope.aliyuncs.com/compatible-mode/v1",
            api_key="secret-key",
        )
    )
    profile = await service.create_profile(
        CreateLLMModelProfileRequest(
            provider_id=provider.id,
            name="Qwen Plus",
            category=ModelProfileCategory.LLM,
            model_id="qwen3.5-plus",
            catalog_model_key="bailian/qwen3.5-plus",
        )
    )

    listed = await service.list_profiles(category=ModelProfileCategory.LLM)
    stored = next(item for item in listed if item.id == profile.id)
    assert stored.reasoning_config is not None
    assert stored.reasoning_config.get("supports_thinking") is True
    assert stored.params is not None

    providers = await service.list_providers()
    assert providers[0].preset_key == "bailian"

    resolved = await service.resolve_profile(profile.id)
    assert resolved.reasoning_config is not None
    assert resolved.reasoning_config.get("supports_thinking") is True
    assert resolved.provider_config == {"thinking_request_mode": "extra_body_thinking"}
    assert resolved.params == stored.params


async def test_update_profile_reset_runtime_from_catalog(async_db_session):
    tenant = await _seed_tenant(async_db_session)
    service = LLMProviderConfigService(tenant.id, async_db_session)

    provider = await service.create_provider(
        CreateLLMProviderRequest(
            display_name="DBX",
            preset_key="databricks-ai-gateway",
            api_base="https://workspace.example.com/ai-gateway/mlflow/v1",
            api_key="secret-key",
        )
    )
    profile = await service.create_profile(
        CreateLLMModelProfileRequest(
            provider_id=provider.id,
            name="GLM Flash",
            category=ModelProfileCategory.LLM,
            model_id="system.ai.glm-5-3-flash",
            catalog_model_key="databricks-ai-gateway/system.ai.glm-5-3-flash",
        )
    )

    await service.update_profile(
        profile.id,
        UpdateLLMModelProfileRequest(
            params={"temperature": 0.9},
            reasoning_config={"supports_thinking": False},
        ),
    )
    overridden = await service.resolve_profile(profile.id)
    assert overridden.params == {"temperature": 0.9}
    assert overridden.reasoning_config == {"supports_thinking": False, "thinking_effort_options": []}

    await service.update_profile(
        profile.id,
        UpdateLLMModelProfileRequest(reset_runtime_from_catalog=True),
    )
    reset = await service.resolve_profile(profile.id)
    assert reset.reasoning_config is not None
    assert reset.reasoning_config.get("supports_thinking") is True
    opts = reset.reasoning_config.get("thinking_effort_options") or []
    assert opts[0]["value"] == "low"
    assert reset.provider_config == {"thinking_request_mode": "reasoning_effort"}

