"""DTO schemas for report APIs."""

from dataclasses import dataclass
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from apps.shared.artifact.schemas import Artifact
from apps.shared.report.domain import ReportFormat


class ReportDTO(BaseModel):
    """Service-layer DTO for report transfer between repository/service/router."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int
    owner_id: int
    source_thread_id: str | None
    title: str
    content: str
    format: ReportFormat
    status: str
    report_metadata: dict = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime
    owner_username: str | None = None


@dataclass
class ReportCreateWithArtifactResult:
    """Result model for report creation with optional thread-level artifact link."""

    report: ReportDTO
    artifact: Artifact | None = None


class ReportResponse(BaseModel):
    """Report API response."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    owner_id: int
    title: str
    content: str
    format: ReportFormat
    source_thread_id: str | None
    metadata: dict = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime
    owner_username: str | None = None
