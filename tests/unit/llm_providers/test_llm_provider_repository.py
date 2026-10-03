"""Tests for LLM provider repository adapters."""

from datetime import UTC, datetime

import pytest

from apps.shared.db.models import LLMProvider, Tenant
from apps.shared.llm_providers.domain import ModelProfileCategory, ModelProfileSource
from apps.shared.llm_providers.repository import LLMModelProfileRepository, LLMProviderRepository

pytestmark = pytest.mark.asyncio


async def _make_tenant(db) -> Tenant:
    tenant = Tenant(name="llm-test-tenant", slug="llm-test-tenant", status="active")
    db.add(tenant)
    await db.flush()
    await db.refresh(tenant)
    return tenant


async def test_create_and_list_provider(async_db_session):
    tenant = await _make_tenant(async_db_session)
    repo = LLMProviderRepository(async_db_session)
    created = await repo.create_provider(
        tenant_id=tenant.id,
        display_name="Bailian Prod",
        preset_key="bailian",
        type="openai-compatible",
        api_base="https://dashscope.example.com/v1",
        embedding_api_base=None,
        api_key_encrypted="encrypted-key",
    )
    await async_db_session.commit()

    providers = await repo.list_providers(tenant.id)
    assert len(providers) == 1
    assert providers[0].id == created.id
    assert providers[0].display_name == "Bailian Prod"
    assert providers[0].preset_key == "bailian"


async def test_create_and_list_model_profile(async_db_session):
    tenant = await _make_tenant(async_db_session)
    provider = LLMProvider(
        tenant_id=tenant.id,
        display_name="Bailian Prod",
        preset_key="bailian",
        type="openai-compatible",
        api_base="https://dashscope.example.com/v1",
        api_key_encrypted="encrypted-key",
        status="active",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    async_db_session.add(provider)
    await async_db_session.flush()

    repo = LLMModelProfileRepository(async_db_session)
    created = await repo.create_profile(
        tenant_id=tenant.id,
        provider_id=provider.id,
        name="Qwen Plus",
        category=ModelProfileCategory.LLM,
        model_id="qwen3.5-plus",
        params={"temperature": 0.1},
        catalog_model_key="bailian/qwen3.5-plus",
        source=ModelProfileSource.PRESET,
    )
    await async_db_session.commit()

    llm_profiles = await repo.list_profiles(tenant.id, category=ModelProfileCategory.LLM)
    embedding_profiles = await repo.list_profiles(tenant.id, category=ModelProfileCategory.EMBEDDING)

    assert len(llm_profiles) == 1
    assert llm_profiles[0].id == created.id
    assert llm_profiles[0].category == ModelProfileCategory.LLM
    assert llm_profiles[0].catalog_model_key == "bailian/qwen3.5-plus"
    assert len(embedding_profiles) == 0


async def test_count_profiles_for_provider(async_db_session):
    tenant = await _make_tenant(async_db_session)
    provider = LLMProvider(
        tenant_id=tenant.id,
        display_name="Provider",
        preset_key="bailian",
        type="openai-compatible",
        api_base="https://dashscope.example.com/v1",
        api_key_encrypted="encrypted-key",
        status="active",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    async_db_session.add(provider)
    await async_db_session.flush()

    profile_repo = LLMModelProfileRepository(async_db_session)
    await profile_repo.create_profile(
        tenant_id=tenant.id,
        provider_id=provider.id,
        name="Profile A",
        category=ModelProfileCategory.LLM,
        model_id="qwen3.5-plus",
        params=None,
        catalog_model_key="bailian/qwen3.5-plus",
        source=ModelProfileSource.PRESET,
    )
    await profile_repo.create_profile(
        tenant_id=tenant.id,
        provider_id=provider.id,
        name="Profile B",
        category=ModelProfileCategory.EMBEDDING,
        model_id="text-embedding-v4",
        params=None,
        catalog_model_key="bailian/text-embedding-v4",
        source=ModelProfileSource.PRESET,
    )
    await async_db_session.commit()

    count = await profile_repo.count_profiles_for_provider(tenant.id, provider.id)
    assert count == 2
