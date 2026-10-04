"""Shared application service for tenant LLM provider registry.

Used by tenant settings APIs and agent runtime resolution (Phase 2).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from apps.shared.core.exceptions import ResourceNotFoundError, ValidationError
from apps.shared.db.models import Tenant
from apps.shared.infra.llm.llm_model_resolver import create_chat_model, create_embeddings
from apps.shared.infra.llm.provider_catalog import get_provider_catalog
from apps.shared.llm_providers.domain import (
    LLMDefaults,
    LLMModelProfileDomain,
    LLMProviderDomain,
    ModelProfileCategory,
    ModelProfileSource,
    ResolvedModelConfig,
)
from apps.shared.llm_providers.dtos import (
    CreateLLMModelProfileRequest,
    CreateLLMProviderRequest,
    LLMDefaultsResponseDTO,
    LLMModelProfileResponseDTO,
    LLMProviderResponseDTO,
    UpdateLLMDefaultsRequest,
    UpdateLLMModelProfileRequest,
    UpdateLLMProviderRequest,
)
from apps.shared.llm_providers.migration import has_legacy_llm_config, migrate_legacy_tenant_config
from apps.shared.llm_providers.repository import LLMModelProfileRepository, LLMProviderRepository
from apps.shared.llm_providers.catalog_dtos import ModelCategory
from apps.shared.utils.field_cipher import FieldCipher
from apps.shared.utils.logger import get_logger

logger = get_logger(__name__)


class LLMProviderConfigService:
    """Tenant-scoped LLM provider and model profile management."""

    def __init__(self, tenant_id: int, db: AsyncSession):
        self.tenant_id = tenant_id
        self.db = db
        self._cipher = FieldCipher()
        self._provider_repo = LLMProviderRepository(db)
        self._profile_repo = LLMModelProfileRepository(db)

    async def ensure_migrated(self) -> None:
        defaults = await self._load_defaults()
        if defaults.to_dict():
            return

        tenant_config = await self._get_tenant_config()
        if not has_legacy_llm_config(tenant_config):
            return

        migrated = await migrate_legacy_tenant_config(
            tenant_id=self.tenant_id,
            tenant_config=tenant_config,
            db=self.db,
        )
        if migrated is None:
            return

        if migrated.to_dict():
            await self._save_defaults(migrated)
        await self._clean_legacy_config()
        await self.db.commit()

    async def resolve_for_agent(self, model_profile_id: int | None, *, mini: bool = False) -> ResolvedModelConfig:
        if model_profile_id is not None:
            profile = await self._require_profile(model_profile_id)
            if profile.category != ModelProfileCategory.LLM:
                raise ValidationError("Agent model profile must have category 'llm'")
            return await self.resolve_profile(model_profile_id)
        return await self.resolve_default_llm_profile(mini=mini)

    # ---------- Providers ----------

    async def list_providers(self) -> list[LLMProviderResponseDTO]:
        await self.ensure_migrated()
        providers = await self._provider_repo.list_providers(self.tenant_id)
        return [self._provider_to_dto(provider) for provider in providers]

    async def create_provider(self, request: CreateLLMProviderRequest) -> LLMProviderResponseDTO:
        if not request.api_key:
            raise ValidationError("api_key is required when creating a provider")

        existing = await self._provider_repo.get_by_display_name(self.tenant_id, request.display_name)
        if existing:
            raise ValidationError(f"Provider '{request.display_name}' already exists")

        preset = get_provider_catalog().get_preset(request.preset_key) if request.preset_key else None
        embedding_api_base = request.embedding_api_base or (preset.embedding_api_base if preset else None)

        provider = await self._provider_repo.create_provider(
            tenant_id=self.tenant_id,
            display_name=request.display_name,
            preset_key=request.preset_key,
            type=request.type,
            api_base=request.api_base,
            embedding_api_base=embedding_api_base,
            api_key_encrypted=self._cipher.encrypt(request.api_key),
        )
        await self.db.commit()
        return self._provider_to_dto(provider)

    async def update_provider(self, provider_id: int, request: UpdateLLMProviderRequest) -> LLMProviderResponseDTO:
        provider = await self._require_provider(provider_id)
        encrypted_key = self._cipher.encrypt(request.api_key) if request.api_key else None

        updated = await self._provider_repo.update_provider(
            provider,
            display_name=request.display_name,
            preset_key=request.preset_key,
            type=request.type,
            api_base=request.api_base,
            embedding_api_base=request.embedding_api_base,
            api_key_encrypted=encrypted_key,
            status=request.status,
        )
        await self.db.commit()
        return self._provider_to_dto(updated)

    async def delete_provider(self, provider_id: int) -> None:
        await self._require_provider(provider_id)
        profile_count = await self._profile_repo.count_profiles_for_provider(self.tenant_id, provider_id)
        if profile_count:
            raise ValidationError("Cannot delete provider while model profiles still reference it")

        await self._provider_repo.delete_provider(self.tenant_id, provider_id)
        await self.db.commit()

    # ---------- Profiles ----------

    async def list_profiles(self, *, category: ModelProfileCategory | None = None) -> list[LLMModelProfileResponseDTO]:
        await self.ensure_migrated()
        profiles = await self._profile_repo.list_profiles(self.tenant_id, category=category)
        return [self._profile_to_dto(profile) for profile in profiles]

    async def create_profile(self, request: CreateLLMModelProfileRequest) -> LLMModelProfileResponseDTO:
        await self._require_provider(request.provider_id)

        existing = await self._profile_repo.get_by_name(self.tenant_id, request.name)
        if existing:
            raise ValidationError(f"Model profile '{request.name}' already exists")

        params = dict(request.params) if request.params else None
        if request.catalog_model_key:
            catalog_profile = get_provider_catalog().get_profile(request.catalog_model_key)
            if catalog_profile and catalog_profile.default_params:
                merged = dict(catalog_profile.default_params)
                if params:
                    merged.update(params)
                params = merged

        source = ModelProfileSource(request.source)
        profile = await self._profile_repo.create_profile(
            tenant_id=self.tenant_id,
            provider_id=request.provider_id,
            name=request.name,
            category=request.category,
            model_id=request.model_id,
            params=params,
            catalog_model_key=request.catalog_model_key,
            source=source,
        )
        await self.db.commit()
        return self._profile_to_dto(profile)

    async def update_profile(self, profile_id: int, request: UpdateLLMModelProfileRequest) -> LLMModelProfileResponseDTO:
        profile = await self._require_profile(profile_id)
        source = ModelProfileSource(request.source) if request.source else None

        updated = await self._profile_repo.update_profile(
            profile,
            name=request.name,
            model_id=request.model_id,
            params=dict(request.params) if request.params is not None else None,
            catalog_model_key=request.catalog_model_key,
            source=source,
        )
        await self.db.commit()
        return self._profile_to_dto(updated)

    async def delete_profile(self, profile_id: int) -> None:
        await self._require_profile(profile_id)
        defaults = await self.get_defaults()
        if profile_id in {
            defaults.agent_profile_id,
            defaults.mini_agent_profile_id,
            defaults.embedding_profile_id,
        }:
            raise ValidationError("Cannot delete a profile that is configured as a tenant default")

        await self._profile_repo.delete_profile(self.tenant_id, profile_id)
        await self.db.commit()

    # ---------- Defaults ----------

    async def get_defaults(self) -> LLMDefaultsResponseDTO:
        await self.ensure_migrated()
        defaults = await self._load_defaults()
        return LLMDefaultsResponseDTO(
            agent_profile_id=defaults.agent_profile_id,
            mini_agent_profile_id=defaults.mini_agent_profile_id,
            embedding_profile_id=defaults.embedding_profile_id,
        )

    async def update_defaults(self, request: UpdateLLMDefaultsRequest) -> LLMDefaultsResponseDTO:
        await self.ensure_migrated()
        current = await self._load_defaults()

        agent_profile_id = request.agent_profile_id if request.agent_profile_id is not None else current.agent_profile_id
        mini_profile_id = (
            request.mini_agent_profile_id
            if request.mini_agent_profile_id is not None
            else current.mini_agent_profile_id
        )
        embedding_profile_id = (
            request.embedding_profile_id
            if request.embedding_profile_id is not None
            else current.embedding_profile_id
        )

        await self._validate_default_profile(agent_profile_id, ModelProfileCategory.LLM)
        await self._validate_default_profile(mini_profile_id, ModelProfileCategory.LLM)
        await self._validate_default_profile(embedding_profile_id, ModelProfileCategory.EMBEDDING)

        defaults = LLMDefaults(
            agent_profile_id=agent_profile_id,
            mini_agent_profile_id=mini_profile_id,
            embedding_profile_id=embedding_profile_id,
        )
        await self._save_defaults(defaults)
        await self.db.commit()
        return LLMDefaultsResponseDTO(
            agent_profile_id=defaults.agent_profile_id,
            mini_agent_profile_id=defaults.mini_agent_profile_id,
            embedding_profile_id=defaults.embedding_profile_id,
        )

    # ---------- Runtime resolution (Phase 2 entry point) ----------

    async def validate_agent_model_profile(self, profile_id: int) -> None:
        """Ensure an agent-bound profile exists, is LLM-scoped, and provider is active."""
        try:
            await self.resolve_for_agent(profile_id)
        except ResourceNotFoundError as exc:
            raise ValidationError(str(exc)) from exc

    async def resolve_profile(self, profile_id: int) -> ResolvedModelConfig:
        await self.ensure_migrated()
        profile = await self._require_profile(profile_id)
        provider = await self._require_provider(profile.provider_id)
        if not provider.is_active():
            raise ValidationError(f"LLM provider '{provider.display_name}' is disabled")

        api_base = provider.embedding_api_base or provider.api_base
        if profile.is_llm():
            api_base = provider.api_base

        return ResolvedModelConfig(
            profile_id=profile.id,
            profile_name=profile.name,
            category=profile.category,
            model_id=profile.model_id,
            params=profile.params,
            provider_id=provider.id,
            provider_display_name=provider.display_name,
            provider_type=provider.type,
            provider_preset_key=provider.preset_key,
            api_base=api_base,
            api_key=self._cipher.decrypt(provider.api_key_encrypted),
        )

    async def resolve_default_llm_profile(self, *, mini: bool = False) -> ResolvedModelConfig:
        defaults = await self._load_defaults()
        profile_id = defaults.mini_agent_profile_id if mini else defaults.agent_profile_id
        if profile_id is None:
            role = "mini agent" if mini else "agent"
            raise ValidationError(f"Default {role} model profile is not configured")
        return await self.resolve_profile(profile_id)

    async def resolve_default_embedding_profile(self) -> ResolvedModelConfig:
        defaults = await self._load_defaults()
        if defaults.embedding_profile_id is None:
            raise ValidationError("Default embedding model profile is not configured")
        return await self.resolve_profile(defaults.embedding_profile_id)

    # ---------- Connection tests ----------

    async def test_profile_connection(self, profile_id: int, api_key: str = "") -> str:
        resolved = await self.resolve_profile(profile_id)
        key = api_key or resolved.api_key
        category = ModelCategory.EMBEDDING if resolved.category == ModelProfileCategory.EMBEDDING else ModelCategory.LLM
        return await self._test_connection(
            api_base=resolved.api_base,
            model_id=resolved.model_id,
            api_key=key,
            category=category,
        )

    async def test_provider_connection(
        self,
        provider_id: int,
        *,
        api_base: str | None = None,
        model_id: str | None = None,
        api_key: str = "",
        category: ModelCategory = ModelCategory.LLM,
    ) -> str:
        """Test provider credentials using a linked profile or catalog preset model."""
        provider = await self._require_provider(provider_id)

        if model_id is None:
            profiles = await self._profile_repo.list_profiles(self.tenant_id)
            linked = [profile for profile in profiles if profile.provider_id == provider_id]
            llm_profile = next((profile for profile in linked if profile.is_llm()), None)
            embedding_profile = next((profile for profile in linked if profile.is_embedding()), None)

            if category == ModelCategory.EMBEDDING and embedding_profile:
                return await self.test_profile_connection(embedding_profile.id, api_key)
            if llm_profile:
                return await self.test_profile_connection(llm_profile.id, api_key)
            if embedding_profile:
                return await self.test_profile_connection(embedding_profile.id, api_key)

            if provider.preset_key:
                catalog_models = get_provider_catalog().list_models(category, provider=provider.preset_key)
                if catalog_models:
                    model_id = catalog_models[0]["model_id"]

        if model_id is None:
            raise ValidationError(
                "Cannot test connection: no model profile linked to this provider. Create a model profile first."
            )

        resolved_api_base = api_base or provider.api_base
        if category == ModelCategory.EMBEDDING:
            resolved_api_base = api_base or provider.embedding_api_base or provider.api_base

        key = api_key or self._cipher.decrypt(provider.api_key_encrypted)
        return await self._test_connection(
            api_base=resolved_api_base,
            model_id=model_id,
            api_key=key,
            category=category,
        )

    async def test_connection(
        self,
        *,
        api_base: str,
        model_id: str,
        api_key: str,
        category: ModelCategory,
        provider_id: int | None = None,
    ) -> str:
        key = api_key
        if not key and provider_id is not None:
            provider = await self._require_provider(provider_id)
            key = self._cipher.decrypt(provider.api_key_encrypted)
        return await self._test_connection(api_base=api_base, model_id=model_id, api_key=key, category=category)

    async def _test_connection(
        self,
        *,
        api_base: str,
        model_id: str,
        api_key: str,
        category: ModelCategory,
    ) -> str:
        if not api_key:
            raise ValidationError("API key is required")
        if not api_base:
            raise ValidationError("API base URL is required")
        if not model_id:
            raise ValidationError("Model ID is required")

        try:
            if category == ModelCategory.EMBEDDING:
                resolved = ResolvedModelConfig(
                    profile_id=0,
                    profile_name="test",
                    category=ModelProfileCategory.EMBEDDING,
                    model_id=model_id,
                    params=None,
                    provider_id=0,
                    provider_display_name="test",
                    provider_type="openai-compatible",
                    provider_preset_key=None,
                    api_base=api_base,
                    api_key=api_key,
                )
                embeddings = create_embeddings(resolved)
                await embeddings.aembed_query("Hello, this is a connection test.")
            else:
                resolved = ResolvedModelConfig(
                    profile_id=0,
                    profile_name="test",
                    category=ModelProfileCategory.LLM,
                    model_id=model_id,
                    params=None,
                    provider_id=0,
                    provider_display_name="test",
                    provider_type="openai-compatible",
                    provider_preset_key=None,
                    api_base=api_base,
                    api_key=api_key,
                )
                llm = create_chat_model(resolved)
                await llm.ainvoke("Hello, this is a connection test. Please respond with 'OK'.")
        except ValidationError:
            raise
        except Exception as exc:
            logger.error("Connection test failed for tenant %s: %s", self.tenant_id, exc, exc_info=True)
            raise ValidationError(f"Connection test failed: {exc}") from exc

        return "Connection test passed"

    # ---------- Internal helpers ----------

    async def _require_provider(self, provider_id: int) -> LLMProviderDomain:
        provider = await self._provider_repo.get_provider(self.tenant_id, provider_id)
        if provider is None:
            raise ResourceNotFoundError(f"LLM provider {provider_id} not found")
        return provider

    async def _require_profile(self, profile_id: int) -> LLMModelProfileDomain:
        profile = await self._profile_repo.get_profile(self.tenant_id, profile_id)
        if profile is None:
            raise ResourceNotFoundError(f"LLM model profile {profile_id} not found")
        return profile

    async def _validate_default_profile(
        self,
        profile_id: int | None,
        expected_category: ModelProfileCategory,
    ) -> None:
        if profile_id is None:
            return
        profile = await self._require_profile(profile_id)
        if profile.category != expected_category:
            raise ValidationError(
                f"Profile {profile_id} has category '{profile.category.value}', expected '{expected_category.value}'"
            )

    async def _get_tenant_row(self) -> Tenant:
        result = await self.db.execute(select(Tenant).where(Tenant.id == self.tenant_id))
        tenant = result.scalar_one_or_none()
        if tenant is None:
            raise ResourceNotFoundError(f"Tenant {self.tenant_id} not found")
        return tenant

    async def _get_tenant_config(self) -> dict[str, Any]:
        tenant = await self._get_tenant_row()
        return tenant.config or {}

    async def _load_defaults(self) -> LLMDefaults:
        tenant_config = await self._get_tenant_config()
        return LLMDefaults.from_dict(tenant_config.get("llm_defaults"))

    async def _save_defaults(self, defaults: LLMDefaults) -> None:
        tenant = await self._get_tenant_row()
        existing_config = tenant.config or {}
        tenant.config = {**existing_config, "llm_defaults": defaults.to_dict()}
        flag_modified(tenant, "config")
        await self.db.flush()

    async def _clean_legacy_config(self) -> None:
        tenant = await self._get_tenant_row()
        config = dict(tenant.config or {})
        changed = False
        for key in ("llm_config", "embedding_config"):
            if key in config:
                del config[key]
                changed = True
        if not changed:
            return
        tenant.config = config
        flag_modified(tenant, "config")
        await self.db.flush()

    def _provider_to_dto(self, provider: LLMProviderDomain) -> LLMProviderResponseDTO:
        decrypted = self._cipher.decrypt(provider.api_key_encrypted)
        return LLMProviderResponseDTO(
            id=provider.id,
            display_name=provider.display_name,
            preset_key=provider.preset_key,
            type=provider.type,
            api_base=provider.api_base,
            embedding_api_base=provider.embedding_api_base,
            api_key_masked=FieldCipher.mask_value(decrypted),
            status=provider.status,
        )

    def _profile_to_dto(self, profile: LLMModelProfileDomain) -> LLMModelProfileResponseDTO:
        return LLMModelProfileResponseDTO(
            id=profile.id,
            provider_id=profile.provider_id,
            name=profile.name,
            category=profile.category,
            model_id=profile.model_id,
            params=profile.params,
            catalog_model_key=profile.catalog_model_key,
            source=profile.source.value,
        )
