"""Adapters for report domain conversions."""

from apps.shared.db.models import Report
from apps.shared.report.domain import ReportDomain, ReportFormat
from apps.shared.report.schemas import ReportDTO


def db_report_to_domain(db_report: Report) -> ReportDomain:
    """Convert Report DB model to ReportDomain."""
    report_format = (
        db_report.format if isinstance(db_report.format, ReportFormat) else ReportFormat(db_report.format)
    )
    return ReportDomain(
        id=db_report.id,
        tenant_id=db_report.tenant_id,
        owner_id=db_report.owner_id,
        source_thread_id=db_report.source_thread_id,
        title=db_report.title,
        content=db_report.content,
        format=report_format,
        status=db_report.status,
        report_metadata=db_report.report_metadata,
        created_at=db_report.created_at,
        updated_at=db_report.updated_at,
        owner_username=db_report.owner_user.username if db_report.owner_user else None,
    )


def domain_report_to_dto(report: ReportDomain) -> ReportDTO:
    """Convert ReportDomain to ReportDTO."""
    return ReportDTO(
        id=report.id,
        tenant_id=report.tenant_id,
        owner_id=report.owner_id,
        source_thread_id=report.source_thread_id,
        title=report.title,
        content=report.content,
        format=report.format,
        status=report.status,
        report_metadata=report.report_metadata,
        created_at=report.created_at,
        updated_at=report.updated_at,
        owner_username=report.owner_username,
    )
