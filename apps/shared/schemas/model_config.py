"""Model configuration DTOs - LLM and Embedding model definitions.

This module provides shared DTOs for model configuration across all layers:
- API router request/response validation
- Service layer business logic
- Infrastructure layer model factory and registry

Moving DTOs here from infra/llm/schemas.py ensures correct Clean Architecture
dependency direction: all layers depend on schemas, not on infra.
"""

from enum import StrEnum

from pydantic import BaseModel, Field, field_validator
from typing_extensions import TypedDict


def _normalize_provider_type(value: str) -> str:
    return "openai-compatible" if value == "databricks" else value


class ModelParamsDTO(TypedDict, total=False):
    """Typed model parameters for API layer."""

    temperature: float
    max_tokens: int
    top_p: float


class ModelConfigDTO(BaseModel):
    """Model configuration for a single LLM model."""

    name: str = Field(..., description="Display name for the model")
    type: str = Field(..., description="Model type: openai-compatible")
    api_base: str = Field(..., description="API base URL")
    api_key: str = Field(..., description="API key (will be encrypted before storage)")
    model_id: str = Field(..., description="Model identifier sent to API")
    params: ModelParamsDTO | None = Field(default=None, description="Model parameters (temperature, max_tokens, top_p)")

    @field_validator("type")
    @classmethod
    def _normalize_type(cls, value: str) -> str:
        return _normalize_provider_type(value)


class ModelConfigResponseDTO(BaseModel):
    """Model configuration for API response (API key masked)."""

    name: str = Field(..., description="Display name for the model")
    type: str = Field(..., description="Model type: openai-compatible")
    api_base: str = Field(..., description="API base URL")
    api_key_masked: str = Field(..., description="Masked API key (e.g., 'sk-***abc')")
    model_id: str = Field(..., description="Model identifier sent to API")
    params: ModelParamsDTO | None = Field(default=None, description="Model parameters")

    @field_validator("type")
    @classmethod
    def _normalize_type(cls, value: str) -> str:
        return _normalize_provider_type(value)


class TenantLLMConfigDTO(BaseModel):
    """Tenant-level LLM configuration containing agent and mini-agent models."""

    agent_model: ModelConfigDTO = Field(..., description="Main agent model configuration")
    mini_agent_model: ModelConfigDTO = Field(..., description="Mini agent model configuration")


class TenantLLMConfigResponseDTO(BaseModel):
    """Tenant LLM configuration for API response (API keys masked)."""

    agent_model: ModelConfigResponseDTO = Field(..., description="Main agent model configuration")
    mini_agent_model: ModelConfigResponseDTO = Field(..., description="Mini agent model configuration")


class ProviderDTO(BaseModel):
    """Provider information for model selection."""

    provider: str = Field(..., description="Provider key (e.g., 'bailian-compatible')")
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


class ProviderWithModelsDTO(BaseModel):
    """Provider with its available models."""

    provider: str = Field(..., description="Provider key")
    name: str = Field(..., description="Provider display name")
    type: str = Field(..., description="Provider type")
    api_base: str | None = Field(default=None, description="Default API base URL")
    api_base_env: str | None = Field(default=None, description="Environment variable for API base")
    models: list[ModelDTO] = Field(default_factory=list, description="Available models for this provider")


class ModelCategory(StrEnum):
    """Model category enumeration for LLM and embedding models."""

    LLM = "llm"
    EMBEDDING = "embedding"


class ProviderWithModelsByCategoryDTO(BaseModel):
    """Provider with its models filtered by category."""

    provider: str = Field(..., description="Provider key")
    name: str = Field(..., description="Provider display name")
    type: str = Field(..., description="Provider type")
    api_base: str | None = Field(default=None, description="Default API base URL")
    api_base_env: str | None = Field(default=None, description="Environment variable for API base")
    embedding_api_base: str | None = Field(default=None, description="Default Embedding API base URL")
    models: list[ModelDTO] = Field(
        default_factory=list, description="Available models for this provider (filtered by category)"
    )


class EmbeddingModelConfigDTO(BaseModel):
    """Embedding model configuration."""

    name: str = Field(default="", description="Display name for the embedding model")
    type: str = Field(default="openai-compatible", description="Model type: openai-compatible")
    api_base: str = Field(..., description="API base URL")
    api_key: str = Field(
        default="", description="API key (will be encrypted before storage). Empty to keep existing key."
    )
    model_id: str = Field(..., description="Embedding model identifier")


class EmbeddingModelConfigResponseDTO(BaseModel):
    """Embedding model configuration for API response (API key masked)."""

    name: str = Field(..., description="Display name for the embedding model")
    type: str = Field(..., description="Model type")
    api_base: str = Field(..., description="API base URL")
    api_key_masked: str = Field(..., description="Masked API key")
    model_id: str = Field(..., description="Embedding model identifier")


class TenantEmbeddingConfigDTO(BaseModel):
    """Tenant-level Embedding model configuration."""

    embedding_model: EmbeddingModelConfigDTO = Field(..., description="Embedding model configuration")


class TenantEmbeddingConfigResponseDTO(BaseModel):
    """Tenant Embedding configuration for API response (API keys masked)."""

    embedding_model: EmbeddingModelConfigResponseDTO = Field(..., description="Embedding model configuration")
