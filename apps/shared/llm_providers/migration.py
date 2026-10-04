"""Migrate legacy tenants.config JSON LLM settings into DB registry tables."""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.infra.llm.provider_catalog import get_provider_catalog
from apps.shared.llm_providers.domain import LLMDefaults, ModelProfileCategory, ModelProfileSource
from apps.shared.llm_providers.repository import LLMModelProfileRepository, LLMProviderRepository
from apps.shared.utils.field_cipher import FieldCipher
from apps.shared.utils.logger import get_logger

logger = get_logger(__name__)


def has_legacy_llm_config(tenant_config: dict[str, Any] | None) -> bool:
    """Return True when tenant.config still carries legacy llm/embedding JSON."""
    if not tenant_config:
        return False
    llm_config = tenant_config.get("llm_config") or {}
    embedding_config = tenant_config.get("embedding_config") or {}
    return bool(
        llm_config.get("agent_model")
        or llm_config.get("mini_agent_model")
        or embedding_config.get("embedding_model")
    )


def _infer_preset_key(api_base: str) -> str | None:
    catalog = get_provider_catalog()
    for preset in catalog.list_presets():
        if preset.api_base and preset.api_base == api_base:
            return preset.key
    return None


def _infer_catalog_model_key(preset_key: str | None, model_id: str, category: ModelProfileCategory) -> str | None:
    if not preset_key:
        return None
    candidate = f"{preset_key}/{model_id}"
    catalog = get_provider_catalog()
    if catalog.get_profile(candidate):
        return candidate
    return None


async def migrate_legacy_tenant_config(
    *,
    tenant_id: int,
    tenant_config: dict[str, Any] | None,
    db: AsyncSession,
) -> LLMDefaults | None:
    """Migrate legacy llm_config / embedding_config JSON into DB rows.

    Returns migrated defaults when legacy config is present, otherwise None.
    Idempotent: reuses existing provider/profile rows matched by credentials or name.
    """
    if not has_legacy_llm_config(tenant_config):
        return None

    provider_repo = LLMProviderRepository(db)
    profile_repo = LLMModelProfileRepository(db)
    cipher = FieldCipher()

    llm_config = tenant_config.get("llm_config") or {}
    embedding_config = tenant_config.get("embedding_config") or {}
    agent_model = llm_config.get("agent_model")
    mini_agent_model = llm_config.get("mini_agent_model")
    embedding_model = embedding_config.get("embedding_model")

    agent_profile_id: int | None = None
    mini_agent_profile_id: int | None = None
    embedding_profile_id: int | None = None
    provider_cache: dict[tuple[str, str], int] = {}

    async def _ensure_provider(model_data: dict[str, Any], *, fallback_name: str) -> int:
        api_base = model_data.get("api_base", "")
        encrypted_key = model_data.get("api_key", "")
        if not api_base or not encrypted_key:
            raise ValueError(f"Cannot migrate provider '{fallback_name}': api_base and api_key are required")

        plain_key = cipher.decrypt(encrypted_key)
        cache_key = (api_base, plain_key)
        if cache_key in provider_cache:
            return provider_cache[cache_key]

        for existing in await provider_repo.list_providers(tenant_id):
            if existing.api_base == api_base and cipher.decrypt(existing.api_key_encrypted) == plain_key:
                provider_cache[cache_key] = existing.id
                return existing.id

        preset_key = _infer_preset_key(api_base)
        preset = get_provider_catalog().get_preset(preset_key) if preset_key else None
        display_name = model_data.get("name") or fallback_name
        created = await provider_repo.create_provider(
            tenant_id=tenant_id,
            display_name=display_name,
            preset_key=preset_key,
            type=model_data.get("type", "openai-compatible"),
            api_base=api_base,
            embedding_api_base=preset.embedding_api_base if preset else None,
            api_key_encrypted=encrypted_key,
        )
        provider_cache[cache_key] = created.id
        return created.id

    async def _ensure_profile(
        *,
        model_data: dict[str, Any],
        provider_id: int,
        profile_name: str,
        category: ModelProfileCategory,
        preset_key: str | None,
    ) -> int:
        existing = await profile_repo.get_by_name(tenant_id, profile_name)
        if existing:
            return existing.id

        model_id = model_data.get("model_id", "")
        catalog_model_key = _infer_catalog_model_key(preset_key, model_id, category)
        created = await profile_repo.create_profile(
            tenant_id=tenant_id,
            provider_id=provider_id,
            name=profile_name,
            category=category,
            model_id=model_id,
            params=model_data.get("params"),
            catalog_model_key=catalog_model_key,
            source=ModelProfileSource.PRESET if catalog_model_key else ModelProfileSource.CUSTOM,
        )
        return created.id

    if agent_model:
        provider_id = await _ensure_provider(agent_model, fallback_name="Agent Provider")
        preset_key = _infer_preset_key(agent_model.get("api_base", ""))
        agent_profile_id = await _ensure_profile(
            model_data=agent_model,
            provider_id=provider_id,
            profile_name=agent_model.get("name") or "Agent Default",
            category=ModelProfileCategory.LLM,
            preset_key=preset_key,
        )

    if mini_agent_model:
        provider_id = await _ensure_provider(mini_agent_model, fallback_name="Mini Agent Provider")
        preset_key = _infer_preset_key(mini_agent_model.get("api_base", ""))
        mini_agent_profile_id = await _ensure_profile(
            model_data=mini_agent_model,
            provider_id=provider_id,
            profile_name=mini_agent_model.get("name") or "Mini Agent Default",
            category=ModelProfileCategory.LLM,
            preset_key=preset_key,
        )

    if embedding_model:
        provider_id = await _ensure_provider(embedding_model, fallback_name="Embedding Provider")
        preset_key = _infer_preset_key(embedding_model.get("api_base", ""))
        embedding_profile_id = await _ensure_profile(
            model_data=embedding_model,
            provider_id=provider_id,
            profile_name=embedding_model.get("name") or "Embedding Default",
            category=ModelProfileCategory.EMBEDDING,
            preset_key=preset_key,
        )

    defaults = LLMDefaults(
        agent_profile_id=agent_profile_id,
        mini_agent_profile_id=mini_agent_profile_id,
        embedding_profile_id=embedding_profile_id,
    )
    logger.info(
        "Migrated legacy LLM config to registry for tenant %s (agent=%s mini=%s embedding=%s)",
        tenant_id,
        defaults.agent_profile_id,
        defaults.mini_agent_profile_id,
        defaults.embedding_profile_id,
    )
    return defaults
