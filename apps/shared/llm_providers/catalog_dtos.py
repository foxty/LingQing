"""Platform catalog DTOs (providers.yaml presets)."""

from enum import StrEnum

from pydantic import BaseModel, Field


class ModelCategory(StrEnum):
    """Model category enumeration for LLM and embedding models."""

    LLM = "llm"
    EMBEDDING = "embedding"


class ProviderDTO(BaseModel):
    """Provider information for model selection."""

    key: str | None = Field(default=None, description="Stable preset key from providers.yaml")
    provider: str = Field(..., description="Provider key (e.g., 'bailian')")
    name: str = Field(..., description="Provider display name (e.g., '阿里云百炼')")
    type: str = Field(..., description="Provider type: openai-compatible")
    api_base: str | None = Field(default=None, description="Default API base URL for this provider")
    api_base_env: str | None = Field(default=None, description="Environment variable name for API base")


class ModelDTO(BaseModel):
    """Model information for selection."""

    key: str = Field(..., description="Model key for reference")
    name: str = Field(..., description="Model display name")
    model_id: str = Field(..., description="Model identifier sent to API")
    default_params: dict | None = Field(default=None, description="Default model parameters")
    metadata: dict | None = Field(default=None, description="Model metadata like description, cost")
    category: str | None = Field(default=None, description="Model category when filtered")


class ProviderWithModelsDTO(BaseModel):
    """Provider with its available models."""

    key: str | None = Field(default=None, description="Stable preset key from providers.yaml")
    provider: str = Field(..., description="Provider key")
    name: str = Field(..., description="Provider display name")
    type: str = Field(..., description="Provider type")
    api_base: str | None = Field(default=None, description="Default API base URL")
    api_base_env: str | None = Field(default=None, description="Environment variable for API base")
    models: list[ModelDTO] = Field(default_factory=list, description="Available models for this provider")


class ProviderWithModelsByCategoryDTO(BaseModel):
    """Provider with its models filtered by category."""

    key: str | None = Field(default=None, description="Stable preset key from providers.yaml")
    provider: str = Field(..., description="Provider key")
    name: str = Field(..., description="Provider display name")
    type: str = Field(..., description="Provider type")
    api_base: str | None = Field(default=None, description="Default API base URL")
    api_base_env: str | None = Field(default=None, description="Environment variable for API base")
    embedding_api_base: str | None = Field(default=None, description="Default Embedding API base URL")
    models: list[ModelDTO] = Field(
        default_factory=list, description="Available models for this provider (filtered by category)"
    )
