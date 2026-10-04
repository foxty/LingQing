"""Tests for shared LLMProviderConfigService."""

import pytest

from apps.shared.core.exceptions import ValidationError
from apps.shared.db.models import Tenant
from apps.shared.llm_providers.domain import ModelProfileCategory
from apps.shared.llm_providers.dtos import (
    CreateLLMModelProfileRequest,
    CreateLLMProviderRequest,
    UpdateLLMDefaultsRequest,
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


async def test_ensure_migrated_with_existing_provider_and_legacy_config(async_db_session):
    cipher = FieldCipher()
    tenant = Tenant(
        name="legacy-after-provider",
        slug="legacy-after-provider",
        status="active",
        config={
            "llm_config": {
                "agent_model": {
                    "name": "Agent Default",
                    "type": "openai-compatible",
                    "api_base": "https://api.deepseek.com",
                    "api_key": cipher.encrypt("test-key"),
                    "model_id": "deepseek-v4-pro",
                }
            }
        },
    )
    async_db_session.add(tenant)
    await async_db_session.flush()

    service = LLMProviderConfigService(tenant.id, async_db_session)
    await service.create_provider(
        CreateLLMProviderRequest(
            display_name="Manual Provider",
            api_base="https://api.example.com/v1",
            api_key="other-key",
        )
    )

    await service.ensure_migrated()
    await async_db_session.refresh(tenant)

    defaults = tenant.config.get("llm_defaults") or {}
    assert defaults.get("agent_profile_id") is not None
    assert "llm_config" not in tenant.config


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

    async def fake_test_connection(**kwargs):
        assert kwargs["model_id"] == "deepseek-v4-pro"
        assert kwargs["api_base"] == "https://api.deepseek.com"
        return "Connection test passed"

    service._test_connection = fake_test_connection  # type: ignore[method-assign]
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
