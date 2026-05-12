"""Domain models for report resources."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from apps.shared.domain.base_domain_model import BaseDomainModel


class ReportFormat(StrEnum):
    """Supported report content formats."""

    MARKDOWN = "markdown"
    HTML = "html"


VALID_REPORT_FORMATS = {ReportFormat.MARKDOWN, ReportFormat.HTML}


@dataclass
class ReportDomain(BaseDomainModel):
    """Domain model for persisted reports."""

    id: int
    tenant_id: int
    owner_id: int
    source_thread_id: str | None
    title: str
    content: str
    format: ReportFormat
    status: str
    report_metadata: dict
    created_at: datetime
    updated_at: datetime
    owner_username: str | None = None
