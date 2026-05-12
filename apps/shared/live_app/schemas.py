"""API DTO schemas for live app endpoints."""

from dataclasses import dataclass

from pydantic import BaseModel, Field

from apps.shared.artifact.schemas import Artifact


class LiveAppQueryRequestDTO(BaseModel):
    sql: str = Field(..., min_length=1)


class LiveAppMutateRequestDTO(BaseModel):
    operation: str = Field(..., min_length=1)
    table: str = Field(..., min_length=1)
    data: dict | list[dict] | None = None
    where: dict | None = None
    id: int | str | None = None


class LiveAppDeploymentStateDTO(BaseModel):
    dev: str | None = None
    test: str | None = None
    prod: str | None = None


class LiveAppRecordDTO(BaseModel):
    app_id: int
    name: str
    description: str | None = None
    entry_file: str
    sdk_version: str
    status: str
    data_source_id: int | None = None
    owner_name: str | None = None
    deployment_state: LiveAppDeploymentStateDTO
    updated_at: str | None = None


class LiveAppListDTO(BaseModel):
    apps: list[LiveAppRecordDTO]
    count: int


@dataclass
class LiveAppCreateWithArtifactResult:
    """Service-layer create result carrying both app and linked artifact."""

    app: "LiveAppRecordDTO"
    artifact: Artifact | None
