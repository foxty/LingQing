"""Tests for legacy LLM config migration."""

import pytest

from apps.shared.db.models import Tenant
from apps.shared.llm_providers.migration import migrate_legacy_tenant_config
from apps.shared.llm_providers.repository import LLMModelProfileRepository, LLMProviderRepository
from apps.shared.utils.field_cipher import FieldCipher

pytestmark = pytest.mark.asyncio


async def test_migrate_legacy_llm_config(async_db_session):
    cipher = FieldCipher()
    tenant = Tenant(
        name="migrate-tenant",
        slug="migrate-tenant",
        status="active",
        config={
            "llm_config": {
                "agent_model": {
                    "name": "Agent Default",
                    "type": "openai-compatible",
                    "api_base": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                    "api_key": cipher.encrypt("test-key"),
                    "model_id": "qwen3.5-plus",
                    "params": {"temperature": 0.1},
                },
                "mini_agent_model": {
                    "name": "Mini Default",
                    "type": "openai-compatible",
                    "api_base": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                    "api_key": cipher.encrypt("test-key"),
                    "model_id": "qwen3.5-flash",
                },
            },
            "embedding_config": {
                "embedding_model": {
                    "name": "Embedding Default",
                    "type": "openai-compatible",
                    "api_base": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                    "api_key": cipher.encrypt("test-key"),
                    "model_id": "text-embedding-v4",
                }
            },
        },
    )
    async_db_session.add(tenant)
    await async_db_session.flush()

    defaults = await migrate_legacy_tenant_config(
        tenant_id=tenant.id,
        tenant_config=tenant.config,
        db=async_db_session,
    )
    await async_db_session.commit()

    assert defaults is not None
    assert defaults.agent_profile_id is not None
    assert defaults.mini_agent_profile_id is not None
    assert defaults.embedding_profile_id is not None

    provider_repo = LLMProviderRepository(async_db_session)
    profile_repo = LLMModelProfileRepository(async_db_session)
    providers = await provider_repo.list_providers(tenant.id)
    profiles = await profile_repo.list_profiles(tenant.id)

    assert len(providers) == 1
    assert providers[0].preset_key == "bailian"
    assert len(profiles) == 3


async def test_migration_is_idempotent(async_db_session):
    cipher = FieldCipher()
    tenant = Tenant(
        name="migrate-tenant-2",
        slug="migrate-tenant-2",
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

    first = await migrate_legacy_tenant_config(
        tenant_id=tenant.id,
        tenant_config=tenant.config,
        db=async_db_session,
    )
    second = await migrate_legacy_tenant_config(
        tenant_id=tenant.id,
        tenant_config=tenant.config,
        db=async_db_session,
    )
    await async_db_session.commit()

    assert first is not None
    assert second is not None
    assert second.agent_profile_id == first.agent_profile_id

    provider_repo = LLMProviderRepository(async_db_session)
    assert len(await provider_repo.list_providers(tenant.id)) == 1
