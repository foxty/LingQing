"""Service layer for scheduled task operations."""

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from apps.config import EnvConfig
from apps.shared.artifact.access import ArtifactAccessGuard
from apps.shared.artifact.domain import ArtifactType
from apps.shared.artifact.lifecycle import ArtifactLifecycle
from apps.shared.artifact.schemas import Artifact
from apps.shared.authz.ta_permissions import TenantAppPermissions
from apps.shared.authz.ta_rbac import role_has_permission
from apps.shared.core.base_service import TenantAwareService
from apps.shared.core.exceptions import ResourceNotFoundError
from apps.shared.db.models import ScheduledTask
from apps.shared.domain.actor import ActorContext
from apps.shared.tasks.adapters import scheduled_task_run_to_response_dto
from apps.shared.tasks.domain import (
    TASK_STATUS_CANCELLED,
    TASK_STATUS_COMPLETED,
    TASK_STATUS_PAUSED,
    TASK_STATUS_PENDING,
    TASK_STATUS_RUNNING,
    TASK_TYPE_AGENT_RUN,
    TASK_TYPE_LIVEAPP_JOB,
    TASK_TYPE_SKILL_CALL,
    ScheduledTaskScheduleType,
    ScheduledTaskType,
    ScheduleSpec,
    TaskConfig,
    normalize_agent_run_task_config,
    normalize_scheduled_task_name,
)
from apps.shared.tasks.repository import ScheduledTaskRepository
from apps.shared.tasks.run_log_writer import RunLogWriter
from apps.shared.tasks.scheduling import compute_next_run_at
from apps.shared.tasks.schemas import ScheduledTaskCreateWithArtifactResult, ScheduledTaskRunResponseDTO
from apps.shared.utils.pagination import PaginationRequest


class ScheduledTaskService(TenantAwareService):
    """Tenant-scoped orchestration for scheduled task lifecycle."""

    def __init__(self, tenant_id: int, db_session: AsyncSession):
        super().__init__(tenant_id=tenant_id, db_session=db_session)
        self.repo = ScheduledTaskRepository(db_session)
        self.artifacts = ArtifactLifecycle(
            db=db_session,
            tenant_id=tenant_id,
            artifact_type=ArtifactType.SCHEDULED_TASK,
            entity_repo=self.repo,
        )

    @classmethod
    def create(cls, tenant_id: int, db_session: AsyncSession) -> "ScheduledTaskService":
        return cls(tenant_id=tenant_id, db_session=db_session)

    def _task_guard(self, actor: ActorContext) -> ArtifactAccessGuard:
        return ArtifactAccessGuard(
            db=self.db_session,
            tenant_id=actor.tenant_id,
            user_id=actor.user_id,
            user_role=actor.user_role,
            artifact_type=ArtifactType.SCHEDULED_TASK.value,
        )

    async def _has_manage(self, *, actor: ActorContext) -> bool:
        return await role_has_permission(
            db=self.db_session,
            tenant_id=actor.tenant_id,
            role_key=actor.user_role,
            permission=TenantAppPermissions.ARTIFACTS_MANAGE,
        )

    async def _ensure_task_artifact(self, *, task: ScheduledTask) -> None:
        await self.artifacts.link_on_create(
            resource_id=task.id,
            owner_id=task.owner_id,
            title=f"Scheduled Task: {task.name}",
            url=f"/scheduled-tasks/{task.id}/embed",
            metadata={
                "task_id": task.id,
                "task_type": task.task_type,
                "schedule_type": task.schedule_type,
                "next_run_at": task.next_run_at.isoformat() if task.next_run_at else None,
                "status": task.status,
            },
        )

    async def require_read_access(self, *, task_id: int, actor: ActorContext) -> ScheduledTask:
        task = await self.repo.get_task_by_id(task_id, tenant_id=self.tenant_id)
        if not task:
            raise ResourceNotFoundError(f"Scheduled task not found: {task_id}")
        try:
            await self._task_guard(actor).require_read(resource_id=task_id)
        except ResourceNotFoundError:
            # Auto-heal missing artifact rows (e.g. legacy/system tasks) and retry ACL check.
            await self._ensure_task_artifact(task=task)
            await self._task_guard(actor).require_read(resource_id=task_id)
        return task

    async def require_write_access(
        self,
        *,
        task_id: int,
        actor: ActorContext,
        allow_shared_write: bool,
    ) -> ScheduledTask:
        task = await self.require_read_access(task_id=task_id, actor=actor)
        await self._task_guard(actor).require_owner_or_manage(
            resource_id=task_id,
            allow_shared_write=allow_shared_write,
        )
        return task

    async def require_owner_access(self, *, task_id: int, actor: ActorContext) -> ScheduledTask:
        return await self.require_write_access(
            task_id=task_id,
            actor=actor,
            allow_shared_write=False,
        )

    async def get_task_for_actor(self, *, task_id: int, actor: ActorContext) -> ScheduledTask:
        return await self.require_read_access(task_id=task_id, actor=actor)

    async def list_tasks_for_actor(
        self,
        *,
        actor: ActorContext,
        status: str | None = None,
        task_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ScheduledTask]:
        has_manage = await self._has_manage(actor=actor)
        return await self.artifacts.list_entities(
            user_id=actor.user_id,
            has_manage=has_manage,
            status=status,
            task_type=task_type,
            limit=limit,
            offset=offset,
        )

    async def list_task_runs_for_actor(
        self,
        *,
        task_id: int,
        actor: ActorContext,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[ScheduledTaskRunResponseDTO], PaginationRequest]:
        await self.require_read_access(task_id=task_id, actor=actor)

        # Get total count first
        runs, total = await self.repo.list_task_runs_with_count(
            task_id=task_id,
            tenant_id=self.tenant_id,
            limit=page_size,
            offset=(page - 1) * page_size,
        )

        # Create pagination object with bounds checking
        pagination = PaginationRequest.with_total(
            page=page,
            page_size=page_size,
            total=total,
        )

        dtos = [scheduled_task_run_to_response_dto(run) for run in runs]
        return dtos, pagination

    async def get_run_for_actor(
        self,
        *,
        task_id: int,
        run_id: int,
        actor: ActorContext,
    ) -> ScheduledTaskRunResponseDTO:
        """Get a single task run, scoped to task, tenant, and access control."""
        await self.require_read_access(task_id=task_id, actor=actor)
        run = await self.repo.get_run_by_id(run_id=run_id, task_id=task_id, tenant_id=self.tenant_id)
        if not run:
            raise ResourceNotFoundError(f"Task run not found: {run_id}")
        return scheduled_task_run_to_response_dto(run)

    async def cancel_task_for_actor(self, *, task_id: int, actor: ActorContext) -> bool:
        await self.require_write_access(task_id=task_id, actor=actor, allow_shared_write=True)
        has_manage = await self._has_manage(actor=actor)
        user_id = None if has_manage else actor.user_id
        task = await self.repo.get_task_by_id(task_id, tenant_id=self.tenant_id, user_id=user_id)
        if not task:
            return False
        if task.status in {TASK_STATUS_RUNNING, TASK_STATUS_COMPLETED, TASK_STATUS_CANCELLED}:
            return False
        return await self.repo.cancel_task(task_id=task_id, tenant_id=self.tenant_id, user_id=user_id)

    async def pause_task_for_actor(self, *, task_id: int, actor: ActorContext) -> bool:
        await self.require_write_access(task_id=task_id, actor=actor, allow_shared_write=True)
        has_manage = await self._has_manage(actor=actor)
        user_id = None if has_manage else actor.user_id
        task = await self.repo.get_task_by_id(task_id, tenant_id=self.tenant_id, user_id=user_id)
        if not task:
            return False
        if task.status not in {TASK_STATUS_PENDING, TASK_STATUS_RUNNING}:
            return False
        return await self.repo.pause_task(task_id=task_id, tenant_id=self.tenant_id, user_id=user_id)

    async def resume_task_for_actor(self, *, task_id: int, actor: ActorContext) -> bool:
        await self.require_write_access(task_id=task_id, actor=actor, allow_shared_write=True)
        has_manage = await self._has_manage(actor=actor)
        user_id = None if has_manage else actor.user_id
        task = await self.repo.get_task_by_id(task_id, tenant_id=self.tenant_id, user_id=user_id)
        if not task:
            return False
        if task.status != TASK_STATUS_PAUSED:
            return False
        next_run_at = compute_next_run_at(
            schedule_type=task.schedule_type,
            schedule_spec=task.schedule_spec,
        )
        if next_run_at is None:
            raise ResourceNotFoundError(f"Scheduled task cannot be resumed: {task_id}")
        return await self.repo.resume_task(
            task_id=task_id,
            tenant_id=self.tenant_id,
            next_run_at=next_run_at,
            user_id=user_id,
        )

    async def run_task_for_actor(self, *, task_id: int, actor: ActorContext) -> bool:
        """Trigger an immediate execution of the task.

        Sets next_run_at to now so the scheduler will pick it up immediately.
        Returns True if the task was queued for execution, False if not eligible.
        """
        await self.require_write_access(task_id=task_id, actor=actor, allow_shared_write=True)
        has_manage = await self._has_manage(actor=actor)
        user_id = None if has_manage else actor.user_id
        task = await self.repo.get_task_by_id(task_id, tenant_id=self.tenant_id, user_id=user_id)
        if not task:
            return False
        if task.status not in {TASK_STATUS_PENDING, TASK_STATUS_PAUSED}:
            return False
        return await self.repo.trigger_immediate_run(
            task_id=task_id,
            tenant_id=self.tenant_id,
            user_id=user_id,
        )

    async def delete_task_for_actor(self, *, task_id: int, actor: ActorContext) -> bool:
        await self.require_owner_access(task_id=task_id, actor=actor)
        has_manage = await self._has_manage(actor=actor)
        deleted = await self.repo.delete_task(
            task_id=task_id,
            tenant_id=self.tenant_id,
            user_id=None if has_manage else actor.user_id,
        )
        if deleted:
            await self.artifacts.delete_cascade(resource_id=task_id)
        return deleted

    async def update_task_for_actor(
        self,
        *,
        task_id: int,
        actor: ActorContext,
        task_description: str | None = None,
        task_type: str | None = None,
        task_config: TaskConfig | None = None,
        schedule_type: ScheduledTaskScheduleType | None = None,
        schedule_spec: ScheduleSpec | None = None,
        next_run_at: datetime | None = None,
        notification_channels: list[str] | None = None,
    ) -> ScheduledTask:
        task = await self.require_write_access(
            task_id=task_id,
            actor=actor,
            allow_shared_write=True,
        )
        # Validate task_type if changing
        if task_type is not None:
            valid_types = {TASK_TYPE_AGENT_RUN, TASK_TYPE_SKILL_CALL, TASK_TYPE_LIVEAPP_JOB}
            if task_type not in valid_types:
                raise ValueError(
                    f"task_type must be one of: {', '.join(sorted(valid_types))}. "
                    "Note: 'system' tasks are managed internally."
                )
        if task.task_type != TASK_TYPE_AGENT_RUN and task_type is not None and task_type != task.task_type:
            raise ValueError("Cannot change task_type for existing non-agent_run tasks")
        if task.status in {TASK_STATUS_RUNNING, TASK_STATUS_CANCELLED, TASK_STATUS_COMPLETED}:
            raise ValueError(
                f"Task cannot be updated in status '{task.status}'. "
                "Running, completed, or cancelled tasks are not updatable."
            )

        if (
            task_description is None
            and task_type is None
            and task_config is None
            and schedule_type is None
            and schedule_spec is None
            and notification_channels is None
        ):
            raise ValueError("No update fields provided")

        current_task_config = dict(task.task_config or {})

        if task_description is not None:
            normalized_name = normalize_scheduled_task_name(task_description)
            current_task_config["task_description"] = normalized_name
            task.name = normalized_name

        if task_config is not None:
            current_task_config = dict(task_config)
            # Validate task_config based on task_type
            effective_task_type = task_type or task.task_type
            if effective_task_type == TASK_TYPE_SKILL_CALL:
                if not current_task_config.get("skill_id"):
                    raise ValueError("task_config must include 'skill_id' for skill_call tasks")
            elif effective_task_type == TASK_TYPE_LIVEAPP_JOB:
                required_keys = ["app_id", "job_name", "entrypoint"]
                missing = [k for k in required_keys if k not in current_task_config]
                if missing:
                    raise ValueError(f"task_config missing required keys for liveapp_job: {missing}")
            elif effective_task_type == TASK_TYPE_AGENT_RUN:
                if "task_description" not in current_task_config:
                    current_task_config["task_description"] = task.name
                if "agent_id" not in current_task_config:
                    current_task_config["agent_id"] = current_task_config.get("agent_id", "")

        effective_task_type = task_type or task.task_type
        if effective_task_type == TASK_TYPE_AGENT_RUN:
            current_task_config = normalize_agent_run_task_config(current_task_config)

        task.task_config = current_task_config
        if task_type is not None:
            task.task_type = task_type
        if schedule_type is not None:
            task.schedule_type = schedule_type
        if schedule_spec is not None:
            task.schedule_spec = schedule_spec
        if schedule_type is not None or schedule_spec is not None:
            task.next_run_at = next_run_at
        if notification_channels is not None:
            task.notification_channels = notification_channels

        await self.db_session.flush()
        return task

    async def create_task_with_artifact(
        self,
        *,
        user_id: int,
        name: str,
        task_type: ScheduledTaskType,
        task_config: TaskConfig,
        schedule_type: ScheduledTaskScheduleType,
        schedule_spec: ScheduleSpec,
        next_run_at: datetime | None,
        notification_channels: list[str] | None,
        thread_id: str | None,
        source_type: str = "agent",
        execution_mode: str = "internal",
        input_params: dict | None = None,
    ) -> ScheduledTaskCreateWithArtifactResult:
        task = await self.repo.create_task(
            tenant_id=self.tenant_id,
            user_id=user_id,
            name=normalize_scheduled_task_name(name),
            task_type=task_type,
            task_config=task_config,
            schedule_type=schedule_type,
            schedule_spec=schedule_spec,
            next_run_at=next_run_at,
            notification_channels=notification_channels,
            source_type=source_type,
            execution_mode=execution_mode,
            input_params=input_params,
        )
        artifact = await self.artifacts.link_on_create(
            resource_id=task.id,
            owner_id=user_id,
            title=f"Scheduled Task: {task.name}",
            url=f"/scheduled-tasks/{task.id}/embed",
            thread_id=thread_id,
            metadata={
                "task_id": task.id,
                "task_type": task.task_type,
                "schedule_type": task.schedule_type,
                "next_run_at": task.next_run_at.isoformat() if task.next_run_at else None,
                "status": task.status,
            },
        )
        return ScheduledTaskCreateWithArtifactResult(task=task, artifact=Artifact.create_scheduled_task(artifact))

    async def get_run_log_content(
        self,
        *,
        task_id: int,
        run_id: int,
        stream: str,
        actor: ActorContext,
    ) -> str:
        """Read log content for a specific task run.

        Args:
            task_id: Scheduled task ID
            run_id: TaskRun ID
            stream: Log stream ('stdout' or 'stderr')
            actor: Current user context for access control

        Returns:
            Log file content as string

        Raises:
            AuthorizationError: If actor doesn't have read access
            ResourceNotFoundError: If task/run not found or log file missing
            ValueError: If stream is invalid or path resolution fails
        """
        from apps.shared.core.exceptions import AuthorizationError

        if stream not in ("stdout", "stderr"):
            raise ValueError("stream must be 'stdout' or 'stderr'.")

        # Verify access to task and run
        await self.require_read_access(task_id=task_id, actor=actor)
        run_dto = await self.get_run_for_actor(task_id=task_id, run_id=run_id, actor=actor)

        # Get relative path from run result DTO
        result = run_dto.result
        relative_path = result.stdout_log_path if stream == "stdout" else result.stderr_log_path
        if not relative_path:
            raise ResourceNotFoundError(f"No {stream} logs available for this run.")

        # Read log content with security validation
        writer = RunLogWriter(EnvConfig.DATA_ROOT_PATH)
        try:
            return writer.read_log_content(relative_path, stream=stream)
        except FileNotFoundError as e:
            raise ResourceNotFoundError(str(e)) from e
        except ValueError as e:
            raise AuthorizationError(str(e)) from e
