"""Pydantic DTOs for skill management API."""

from __future__ import annotations

from pydantic import BaseModel, Field


class SkillInfo(BaseModel):
    name: str = Field(..., description="Skill name")
    type: str = Field(..., description="Skill type: builtin/tenant/personal")
    description: str = Field(default="", description="Skill description")
    enabled: bool = Field(default=True, description="Whether skill is enabled")
    env_var_keys: list[str] = Field(default_factory=list, description="Environment variable keys (values masked)")
    created_by: str = Field(default="", description="Creator user UUID")
    created_at: str = Field(default="", description="Creation timestamp")
    updated_at: str = Field(default="", description="Last update timestamp")


class SkillToggleRequest(BaseModel):
    enabled: bool = Field(..., description="New enabled state")


class SkillListResponse(BaseModel):
    items: list[SkillInfo] = Field(..., description="List of skills")
    total: int = Field(..., description="Total count")


class EnvVarUpdateRequest(BaseModel):
    env_vars: dict[str, str] = Field(
        ..., description="Environment variables key-value pairs", examples=[{"API_KEY": "sk-xxx"}]
    )


class EnvVarListResponse(BaseModel):
    env_vars: dict[str, str] = Field(..., description="Environment variables with masked values")


class SkillCreateResponse(BaseModel):
    name: str = Field(..., description="Created skill name")
    type: str = Field(..., description="Skill type")
    message: str = Field(default="Skill created successfully")


class SkillImportRequest(BaseModel):
    url: str = Field(..., description="skills.sh or GitHub URL to import")
