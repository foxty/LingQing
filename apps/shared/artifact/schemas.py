"""DTO schemas for shared artifact APIs."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from apps.shared.artifact.domain import ArtifactType


class Artifact(BaseModel):
    """Artifact protocol DTO for tool/UI rendering."""

    type: str = Field(default="artifact", description="Type discriminator, always 'artifact'")
    artifact_type: ArtifactType = Field(description="Specific artifact type for rendering")
    id: int = Field(description="Artifact database record ID")
    url: str | None = Field(default=None, description="Optional URL for iframe rendering or API endpoint")
    title: str = Field(description="Display title for the artifact")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional type-specific metadata")

    @staticmethod
    def _metadata(artifact: Any) -> dict[str, Any]:
        metadata = getattr(artifact, "artifact_metadata", None)
        return metadata or {}

    @classmethod
    def create_dashboard(cls, artifact: Any) -> "Artifact":
        return cls(
            artifact_type=ArtifactType.DASHBOARD,
            id=artifact.id,
            url=artifact.url or f"/dashboards/{artifact.resource_id}/embed",
            title=artifact.title or "Dashboard",
            metadata=cls._metadata(artifact),
        )

    @classmethod
    def create_chart(cls, artifact: Any) -> "Artifact":
        return cls(
            artifact_type=ArtifactType.CHART,
            id=artifact.id,
            url=artifact.url or "",
            title=artifact.title or "Chart",
            metadata=cls._metadata(artifact),
        )

    @classmethod
    def create_report(cls, artifact: Any) -> "Artifact":
        return cls(
            artifact_type=ArtifactType.REPORT,
            id=artifact.id,
            url=artifact.url or f"/reports/{artifact.resource_id}/embed",
            title=artifact.title or "Report",
            metadata=cls._metadata(artifact),
        )

    @classmethod
    def create_scheduled_task(cls, artifact: Any) -> "Artifact":
        return cls(
            artifact_type=ArtifactType.SCHEDULED_TASK,
            id=artifact.id,
            url=artifact.url,
            title=artifact.title or "Scheduled Task",
            metadata=cls._metadata(artifact),
        )

    @classmethod
    def create_live_app(cls, artifact: Any) -> "Artifact":
        return cls(
            artifact_type=ArtifactType.APP,
            id=artifact.id,
            url=artifact.url or f"/api/apps/{artifact.resource_id}/dev/embed",
            title=artifact.title or "Live App",
            metadata=cls._metadata(artifact),
        )


class ArtifactResponse(BaseModel):
    """Artifact response DTO shared across artifact/thread endpoints."""

    model_config = ConfigDict(from_attributes=True)

    type: str = Field(default="artifact", description="Type discriminator")
    artifact_type: str = Field(..., description="Artifact type (dashboard, chart, etc.)")
    id: int = Field(..., description="Artifact record ID")
    resource_id: int = Field(..., description="Underlying resource ID for ACL and deep links")
    url: str | None = Field(None, description="Artifact URL")
    title: str = Field(..., description="Artifact title")
    metadata: dict = Field(default_factory=dict, alias="artifact_metadata", description="Additional metadata")
    created_at: datetime = Field(..., description="Creation timestamp")
    owner_username: str | None = Field(None, description="Canonical owner username")
    is_owner: bool = Field(default=True, description="Whether current user is the creator")
    share_permission: str | None = Field(None, description="Permission level if shared (read/write), None if owner")
