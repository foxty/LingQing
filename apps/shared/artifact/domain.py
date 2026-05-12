"""Domain models for shared artifact module."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from apps.shared.domain.base_domain_model import BaseDomainModel


class ArtifactType(StrEnum):
    """Supported artifact types."""

    DASHBOARD = "dashboard"
    CHART = "chart"
    REPORT = "report"
    DATA_PREVIEW = "data_preview"
    CODE = "code"
    IFRAME = "iframe"
    APP = "app"
    SCHEDULED_TASK = "scheduled_task"


@dataclass
class ArtifactDomain(BaseDomainModel):
    """Artifact domain model."""

    id: int
    thread_id: str | None
    tenant_id: int | None
    owner_id: int
    artifact_type: str
    resource_id: int
    title: str | None
    url: str | None
    artifact_metadata: dict
    created_at: datetime
    updated_at: datetime
    owner_username: str | None = None

    def generate_context_message(self) -> str:
        context_lines = [
            "[Context] The user is currently working with an artifact:",
            f"- Type: {self.artifact_type}",
            f"- Title: {self.title}",
            f"- URL: {self.url}",
            "Please use relevant role or correct responses that are relevant to this artifact context.",
        ]
        return "\n".join(context_lines)
