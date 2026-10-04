"""Domain models and ports for tenant LLM provider configuration."""

from __future__ import annotations

import enum
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from apps.shared.core.exceptions import ValidationError
from apps.shared.domain.base_domain_model import BaseDomainModel


class ModelProfileCategory(enum.StrEnum):
    LLM = "llm"
    EMBEDDING = "embedding"


class ModelProfileSource(enum.StrEnum):
    PRESET = "preset"
    CUSTOM = "custom"


class LLMProviderStatus(enum.StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"


@dataclass
class LLMProviderDomain(BaseDomainModel):
    """Tenant-configured LLM provider credentials."""

    id: int
    tenant_id: int
    display_name: str
    preset_key: str | None
    type: str
    api_base: str
    embedding_api_base: str | None
    api_key_encrypted: str
    status: str
    created_at: datetime
    updated_at: datetime

    def is_active(self) -> bool:
        return self.status == LLMProviderStatus.ACTIVE


@dataclass
class LLMModelProfileDomain(BaseDomainModel):
    """Tenant-configured model profile bound to a provider."""

    id: int
    tenant_id: int
    provider_id: int
    name: str
    category: ModelProfileCategory
    model_id: str
    params: dict[str, Any] | None
    catalog_model_key: str | None
    source: ModelProfileSource
    created_at: datetime
    updated_at: datetime

    def validate_category(self) -> None:
        if self.category not in ModelProfileCategory:
            raise ValidationError(f"Invalid model profile category: {self.category}")

    def is_llm(self) -> bool:
        return self.category == ModelProfileCategory.LLM

    def is_embedding(self) -> bool:
        return self.category == ModelProfileCategory.EMBEDDING


@dataclass(frozen=True)
class LLMDefaults:
    """Tenant default model profile references stored in tenants.config.llm_defaults."""

    agent_profile_id: int | None = None
    mini_agent_profile_id: int | None = None
    embedding_profile_id: int | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> LLMDefaults:
        if not data:
            return cls()
        return cls(
            agent_profile_id=data.get("agent_profile_id"),
            mini_agent_profile_id=data.get("mini_agent_profile_id"),
            embedding_profile_id=data.get("embedding_profile_id"),
        )

    def to_dict(self) -> dict[str, int]:
        result: dict[str, int] = {}
        if self.agent_profile_id is not None:
            result["agent_profile_id"] = self.agent_profile_id
        if self.mini_agent_profile_id is not None:
            result["mini_agent_profile_id"] = self.mini_agent_profile_id
        if self.embedding_profile_id is not None:
            result["embedding_profile_id"] = self.embedding_profile_id
        return result


@dataclass(frozen=True)
class ResolvedModelConfig:
    """Runtime-ready model config after resolving profile + provider."""

    profile_id: int
    profile_name: str
    category: ModelProfileCategory
    model_id: str
    params: dict[str, Any] | None
    provider_id: int
    provider_display_name: str
    provider_type: str
    provider_preset_key: str | None
    api_base: str
    api_key: str


class LLMProviderRepositoryPort(Protocol):
    async def list_providers(self, tenant_id: int) -> list[LLMProviderDomain]: ...

    async def get_provider(self, tenant_id: int, provider_id: int) -> LLMProviderDomain | None: ...

    async def delete_provider(self, tenant_id: int, provider_id: int) -> None: ...


class LLMModelProfileRepositoryPort(Protocol):
    async def list_profiles(
        self,
        tenant_id: int,
        *,
        category: ModelProfileCategory | None = None,
    ) -> list[LLMModelProfileDomain]: ...

    async def get_profile(self, tenant_id: int, profile_id: int) -> LLMModelProfileDomain | None: ...

    async def delete_profile(self, tenant_id: int, profile_id: int) -> None: ...

    async def count_profiles_for_provider(self, tenant_id: int, provider_id: int) -> int: ...
