"""Service layer for persisted reports."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.artifact.access import ArtifactAccessGuard
from apps.shared.artifact.domain import ArtifactType
from apps.shared.artifact.lifecycle import ArtifactLifecycle
from apps.shared.artifact.schemas import Artifact
from apps.shared.authz.ta_permissions import TenantAppPermissions
from apps.shared.authz.ta_rbac import role_has_permission
from apps.shared.core.exceptions import AuthorizationError, ResourceNotFoundError
from apps.shared.core.transaction import transaction
from apps.shared.db.models import ChatThread
from apps.shared.domain.actor import ActorContext
from apps.shared.report.adapters import domain_report_to_dto
from apps.shared.report.repository import ReportRepository
from apps.shared.report.schemas import ReportCreateWithArtifactResult, ReportDTO


class ReportService:
    """Business service for report CRUD."""

    def __init__(self, tenant_id: int, report_repo: ReportRepository, db: AsyncSession):
        self.tenant_id = tenant_id
        self.report_repo = report_repo
        self.db = db
        self.artifacts = ArtifactLifecycle(
            db=db,
            tenant_id=tenant_id,
            artifact_type=ArtifactType.REPORT,
            entity_repo=report_repo,
        )

    @classmethod
    def create(cls, tenant_id: int, db_session: AsyncSession) -> "ReportService":
        return cls(tenant_id=tenant_id, report_repo=ReportRepository(db_session), db=db_session)

    def _report_guard(self, actor: ActorContext) -> ArtifactAccessGuard:
        return ArtifactAccessGuard(
            db=self.db,
            tenant_id=actor.tenant_id,
            user_id=actor.user_id,
            user_role=actor.user_role,
            artifact_type=ArtifactType.REPORT.value,
        )

    async def _has_manage(self, *, actor: ActorContext) -> bool:
        return await role_has_permission(
            db=self.db,
            tenant_id=actor.tenant_id,
            role_key=actor.user_role,
            permission=TenantAppPermissions.ARTIFACTS_MANAGE,
        )

    async def require_read_access(self, *, report_id: int, actor: ActorContext) -> None:
        await self._report_guard(actor).require_read(resource_id=report_id)

    async def require_write_access(self, *, report_id: int, actor: ActorContext) -> None:
        await self._report_guard(actor).require_write(resource_id=report_id)

    async def require_owner_access(self, *, report_id: int, actor: ActorContext) -> None:
        await self._report_guard(actor).require_owner_or_manage(
            resource_id=report_id,
            allow_shared_write=False,
        )

    async def get_report_for_actor(self, report_id: int, *, actor: ActorContext) -> ReportDTO:
        await self.require_read_access(report_id=report_id, actor=actor)
        return await self._get_report(report_id)

    async def list_reports_for_actor(
        self,
        *,
        actor: ActorContext,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ReportDTO]:
        has_manage = await self._has_manage(actor=actor)
        reports = await self.artifacts.list_entities(
            user_id=actor.user_id,
            has_manage=has_manage,
            limit=limit,
            offset=offset,
        )
        return [domain_report_to_dto(report) for report in reports]

    @transaction
    async def delete_report_for_actor(self, report_id: int, *, actor: ActorContext) -> None:
        await self.require_owner_access(report_id=report_id, actor=actor)
        has_manage = await self._has_manage(actor=actor)
        report = await self._get_report(report_id)
        if not has_manage and report.owner_id != actor.user_id:
            raise AuthorizationError("You do not have permission to delete this report")

        await self.artifacts.delete_cascade(resource_id=report_id)
        deleted = await self.report_repo.delete_by_id(report_id=report_id, tenant_id=self.tenant_id)
        if not deleted:
            raise ResourceNotFoundError(f"Report {report_id} not found")

    @transaction
    async def update_report_for_actor(
        self,
        report_id: int,
        *,
        actor: ActorContext,
        title: str | None = None,
        content: str | None = None,
        format: str | None = "markdown",
        report_metadata: dict | None = None,
    ) -> ReportDTO:
        await self.require_owner_access(report_id=report_id, actor=actor)
        has_manage = await self._has_manage(actor=actor)
        report = await self._get_report(report_id)
        if not has_manage and report.owner_id != actor.user_id:
            raise AuthorizationError("You do not have permission to update this report")

        updated = await self.report_repo.update_report(
            report_id,
            title=title,
            content=content,
            format=format,
            report_metadata=report_metadata,
        )
        return domain_report_to_dto(updated)

    @transaction
    async def create_report(
        self,
        title: str,
        content: str,
        owner_id: int,
        format: str = "markdown",
        thread_id: str | None = None,
        report_metadata: dict | None = None,
    ) -> ReportCreateWithArtifactResult:
        report = await self.report_repo.create_report(
            tenant_id=self.tenant_id,
            owner_id=owner_id,
            title=title,
            content=content,
            format=format,
            source_thread_id=thread_id,
            report_metadata=report_metadata,
        )

        report_dto = domain_report_to_dto(report)

        artifact: Artifact | None = None
        if thread_id:
            thread_result = await self.db.execute(select(ChatThread).where(ChatThread.id == thread_id))
            thread = thread_result.scalar_one_or_none()
            if not thread or thread.tenant_id != self.tenant_id:
                raise ResourceNotFoundError(f"Thread {thread_id} not found")
            if thread.user_id != owner_id:
                raise AuthorizationError("Access denied")

        artifact = await self.artifacts.link_on_create(
            resource_id=report_dto.id,
            owner_id=owner_id,
            title=report_dto.title,
            url=f"/reports/{report_dto.id}/embed",
            thread_id=thread_id,
            metadata={"report_id": report_dto.id, "format": report_dto.format},
        )
        artifact_dto = Artifact.create_report(artifact)

        return ReportCreateWithArtifactResult(report=report_dto, artifact=artifact_dto)

    async def _get_report(self, report_id: int) -> ReportDTO:
        report = await self.report_repo.get_by_id(report_id)
        if not report or report.tenant_id != self.tenant_id:
            raise ResourceNotFoundError(f"Report {report_id} not found")
        return domain_report_to_dto(report)
