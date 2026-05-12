"""Repository for persisted reports."""

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from apps.shared.artifact.domain import ArtifactType
from apps.shared.artifact.mixins import ArtifactAwareMixin
from apps.shared.db.models import Report
from apps.shared.report.adapters import db_report_to_domain
from apps.shared.report.domain import ReportDomain


class ReportRepository(ArtifactAwareMixin):
    """Data access layer for report resources."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.model = Report
        self._artifact_type = ArtifactType.REPORT
        self._entity_model = Report
        self._session = db

    async def create_report(
        self,
        tenant_id: int,
        title: str,
        content: str,
        owner_id: int,
        format: str = "markdown",
        source_thread_id: str | None = None,
        report_metadata: dict | None = None,
    ) -> ReportDomain:
        report = Report(
            tenant_id=tenant_id,
            owner_id=owner_id,
            source_thread_id=source_thread_id,
            title=title,
            content=content,
            format=format,
            report_metadata=report_metadata or {},
        )
        self.db.add(report)
        await self.db.flush()
        await self.db.refresh(report)
        return db_report_to_domain(report)

    async def get_by_id(self, report_id: int) -> ReportDomain | None:
        stmt = select(Report).where(Report.id == report_id).options(joinedload(Report.owner_user))
        result = await self.db.execute(stmt)
        report = result.scalar_one_or_none()
        return db_report_to_domain(report) if report else None

    async def list_for_tenant(
        self,
        tenant_id: int,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ReportDomain]:
        """All reports in the tenant (caller must have verified ``artifacts.manage``)."""
        return await self._list_entities(
            tenant_id=tenant_id,
            user_id=None,
            configure=lambda stmt: (
                stmt.options(joinedload(Report.owner_user))
                .order_by(Report.created_at.desc())
                .limit(limit)
                .offset(offset)
            ),
            mapper=db_report_to_domain,
        )

    async def list_for_user_access(
        self,
        *,
        tenant_id: int,
        user_id: int,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ReportDomain]:
        """Reports the user owns or has been shared via artifact shares."""
        return await self._list_entities(
            tenant_id=tenant_id,
            user_id=user_id,
            configure=lambda stmt: (
                stmt.options(joinedload(Report.owner_user))
                .order_by(Report.created_at.desc())
                .limit(limit)
                .offset(offset)
            ),
            mapper=db_report_to_domain,
        )

    async def update_report(
        self,
        report_id: int,
        *,
        title: str | None = None,
        content: str | None = None,
        format: str | None = None,
        report_metadata: dict | None = None,
    ) -> ReportDomain | None:
        stmt = select(Report).where(Report.id == report_id).options(joinedload(Report.owner_user))
        result = await self.db.execute(stmt)
        report = result.scalar_one_or_none()
        if not report:
            return None

        if title is not None:
            report.title = title
        if content is not None:
            report.content = content
        if format is not None:
            report.format = format
        if report_metadata is not None:
            report.report_metadata = report_metadata

        await self.db.flush()
        await self.db.refresh(report)
        return db_report_to_domain(report)

    async def delete_by_id(self, report_id: int, tenant_id: int) -> bool:
        stmt = delete(Report).where(Report.id == report_id, Report.tenant_id == tenant_id)
        result = await self.db.execute(stmt)
        await self.db.flush()
        return result.rowcount > 0
