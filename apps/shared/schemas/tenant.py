"""Shared DTOs for tenant domain."""

from pydantic import BaseModel, Field


class LLMDefaultsDTO(BaseModel):
    agent_profile_id: int | None = None
    mini_agent_profile_id: int | None = None
    embedding_profile_id: int | None = None


class TenantConfigDTO(BaseModel):
    """Tenant configuration aggregate."""

    llm_defaults: LLMDefaultsDTO | None = Field(default=None, description="Default model profile IDs")


class TenantDTO(BaseModel):
    """Tenant DTO."""

    id: int
    name: str
    slug: str
    description: str
    config: TenantConfigDTO | None = Field(
        default=None,
        description="Tenant configuration (optional, may be excluded for list views)",
    )
