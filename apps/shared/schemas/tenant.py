"""Shared DTOs for tenant domain."""

from pydantic import BaseModel, Field

from apps.shared.schemas.model_config import TenantEmbeddingConfigDTO, TenantLLMConfigDTO


class TenantConfigDTO(BaseModel):
    """Tenant configuration aggregate - combines infrastructure layer configs."""

    llm_config: TenantLLMConfigDTO | None = Field(default=None, description="LLM model configuration")
    embedding_config: TenantEmbeddingConfigDTO | None = Field(default=None, description="Embedding model configuration")


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