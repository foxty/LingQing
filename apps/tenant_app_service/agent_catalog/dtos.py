"""DTOs for custom agent catalog."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AgentCapabilityConfigDTO(BaseModel):
    default_tools: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    knowledge_base_ids: list[int] = Field(default_factory=list)
    data_source_ids: list[int] = Field(default_factory=list)
    api_connector_ids: list[int] = Field(default_factory=list)
    model_key: str | None = None


class AgentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None = None
    system_prompt: str
    config: AgentCapabilityConfigDTO
    tags: list[str] = Field(default_factory=list)
    example_questions: list[str] = Field(default_factory=list)
    status: str
    owner_id: int | None = None
    is_system: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None
    can_write: bool = False
    can_manage: bool = False


class AgentCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = None
    system_prompt: str = Field(..., min_length=1)
    config: AgentCapabilityConfigDTO = Field(default_factory=AgentCapabilityConfigDTO)
    tags: list[str] = Field(default_factory=list)
    example_questions: list[str] = Field(default_factory=list)


class AgentUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    system_prompt: str | None = None
    config: AgentCapabilityConfigDTO | None = None
    tags: list[str] | None = None
    example_questions: list[str] | None = None
    status: str | None = None


class AgentSkillCatalogItem(BaseModel):
    name: str
    description: str = ""
    scope: str
    tools: list[str] = Field(default_factory=list)
