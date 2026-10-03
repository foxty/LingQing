"""DTOs for tenant LLM provider registry API."""

from pydantic import BaseModel, Field
from typing_extensions import TypedDict

from apps.shared.llm_providers.catalog_dtos import ModelCategory
from apps.shared.llm_providers.domain import ModelProfileCategory


class ModelParamsDTO(TypedDict, total=False):
    """Typed model parameters for profile create/update requests."""

    temperature: float
    max_tokens: int
    top_p: float


class CreateLLMProviderRequest(BaseModel):
    display_name: str = Field(..., min_length=1, max_length=100)
    preset_key: str | None = None
    type: str = "openai-compatible"
    api_base: str = Field(..., min_length=1, max_length=1024)
    embedding_api_base: str | None = Field(default=None, max_length=1024)
    api_key: str = ""


class UpdateLLMProviderRequest(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=100)
    preset_key: str | None = None
    type: str | None = None
    api_base: str | None = Field(default=None, min_length=1, max_length=1024)
    embedding_api_base: str | None = Field(default=None, max_length=1024)
    api_key: str = ""
    status: str | None = None


class LLMProviderResponseDTO(BaseModel):
    id: int
    display_name: str
    preset_key: str | None
    type: str
    api_base: str
    embedding_api_base: str | None
    api_key_masked: str
    status: str


class CreateLLMModelProfileRequest(BaseModel):
    provider_id: int
    name: str = Field(..., min_length=1, max_length=100)
    category: ModelProfileCategory
    model_id: str = Field(..., min_length=1, max_length=255)
    params: ModelParamsDTO | None = None
    catalog_model_key: str | None = None
    source: str = "preset"


class UpdateLLMModelProfileRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    model_id: str | None = Field(default=None, min_length=1, max_length=255)
    params: ModelParamsDTO | None = None
    catalog_model_key: str | None = None
    source: str | None = None


class LLMModelProfileResponseDTO(BaseModel):
    id: int
    provider_id: int
    name: str
    category: ModelProfileCategory
    model_id: str
    params: dict | None
    catalog_model_key: str | None
    source: str


class LLMDefaultsResponseDTO(BaseModel):
    agent_profile_id: int | None = None
    mini_agent_profile_id: int | None = None
    embedding_profile_id: int | None = None


class UpdateLLMDefaultsRequest(BaseModel):
    agent_profile_id: int | None = None
    mini_agent_profile_id: int | None = None
    embedding_profile_id: int | None = None


class TestModelProfileRequest(BaseModel):
    api_key: str = ""


class TestProviderConnectionRequest(BaseModel):
    api_base: str | None = None
    model_id: str | None = None
    api_key: str = ""
    category: ModelCategory = ModelCategory.LLM
