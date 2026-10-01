"""Repository for unified scheduled tasks."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import Select, and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from apps.shared.artifact.domain import ArtifactType
from apps.shared.artifact.mixins import ArtifactAwareMixin
from apps.shared.db.models import ScheduledTask, TaskRun
from apps.shared.tasks.domain import (
    TASK_RUN_STATUS_FAILED,
    TASK_RUN_STATUS_RUNNING,
    TASK_RUN_STATUS_SUCCESS,
    TASK_STATUS_CANCELLED,
    TASK_STATUS_PAUSED,
    TASK_STATUS_PENDING,
    TASK_STATUS_RUNNING,
    ScheduledTaskScheduleType,
    ScheduledTaskStatus,
    ScheduledTaskType,
    ScheduleSpec,
    TaskConfig,
)


class ScheduledTaskRepository(ArtifactAwareMixin):
    """Data access for scheduled task lifecycle and run history."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.model = ScheduledTask
        self._artifact_type = ArtifactType.SCHEDULED_TASK
        self._entity_model = ScheduledTask
        self._session = session
        self._owner_column = "user_id"

    async def create_task(
        self,
        *,
        tenant_id: int,
        user_id: int,
        name: str,
        task_type: ScheduledTaskType,
        task_config: TaskConfig,
        schedule_type: ScheduledTaskScheduleType,
        schedule_spec: ScheduleSpec,
        next_run_at: datetime | None,
        notification_channels: list[str] | None,
        execution_mode: str = "internal",
        handler_ref: str | None = None,
        input_params: dict | None = None,
    ) -> ScheduledTask:
        task = ScheduledTask(
            tenant_id=tenant_id,
            owner_id=user_id,
            user_id=user_id,
            name=name,
            task_type=task_type,
            task_config=task_config,
            schedule_type=schedule_type,
            schedule_spec=schedule_spec,
            status=TASK_STATUS_PENDING,
            next_run_at=next_run_at,
            notification_channels=notification_channels,
            execution_mode=execution_mode,
            handler_ref=handler_ref,
            input_params=input_params,
        )
        self.session.add(task)
        await self.session.flush()
        await self.session.refresh(task)
        return task

    async def get_task_by_id(
        self,
        task_id: int,
        *,
        tenant_id: int | None = None,
        user_id: int | None = None,
    ) -> ScheduledTask | None:
        stmt: Select = (
            select(ScheduledTask).options(selectinload(ScheduledTask.owner_user)).where(ScheduledTask.id == task_id)
        )
        if tenant_id is not None:
            stmt = stmt.where(ScheduledTask.tenant_id == tenant_id)
        if user_id is not None:
            stmt = stmt.where(ScheduledTask.user_id == user_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_user_tasks(
        self,
        *,
        tenant_id: int,
        user_id: int,
        status: ScheduledTaskStatus | None = None,
        task_type: ScheduledTaskType | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ScheduledTask]:
        stmt = (
            select(ScheduledTask)
            .where(
                ScheduledTask.tenant_id == tenant_id,
                ScheduledTask.user_id == user_id,
            )
            .order_by(ScheduledTask.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        if status:
            stmt = stmt.where(ScheduledTask.status == status)
        if task_type:
            stmt = stmt.where(ScheduledTask.task_type == task_type)

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    def _apply_user_task_scope(stmt):
        return stmt.where(ScheduledTask.stable_key.is_(None))

    async def list_for_tenant(
        self,
        *,
        tenant_id: int,
        status: ScheduledTaskStatus | None = None,
        task_type: ScheduledTaskType | None = None,
        limit: int = 50,
        offset: int = 0,
        user_tasks_only: bool = True,
    ) -> list[ScheduledTask]:
        def _configure(stmt):
            scoped = (
                stmt.options(selectinload(ScheduledTask.owner_user))
                .order_by(ScheduledTask.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
            if user_tasks_only:
                scoped = self._apply_user_task_scope(scoped)
            if status:
                scoped = scoped.where(ScheduledTask.status == status)
            if task_type:
                scoped = scoped.where(ScheduledTask.task_type == task_type)
            return scoped

        return await self._list_entities(tenant_id=tenant_id, user_id=None, configure=_configure)

    async def list_for_user_access(
        self,
        *,
        tenant_id: int,
        user_id: int,
        status: ScheduledTaskStatus | None = None,
        task_type: ScheduledTaskType | None = None,
        limit: int = 50,
        offset: int = 0,
        user_tasks_only: bool = True,
    ) -> list[ScheduledTask]:
        def _configure(stmt):
            scoped = (
                stmt.options(selectinload(ScheduledTask.owner_user))
                .order_by(ScheduledTask.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
            if user_tasks_only:
                scoped = self._apply_user_task_scope(scoped)
            if status:
                scoped = scoped.where(ScheduledTask.status == status)
            if task_type:
                scoped = scoped.where(ScheduledTask.task_type == task_type)
            return scoped

        return await self._list_entities(
            tenant_id=tenant_id,
            user_id=user_id,
            configure=_configure,
        )

    async def list_system_tasks(
        self,
        *,
        tenant_id: int,
        status: ScheduledTaskStatus | None = None,
        task_type: ScheduledTaskType | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ScheduledTask]:
        stmt = (
            select(ScheduledTask)
            .where(
                ScheduledTask.tenant_id == tenant_id,
                ScheduledTask.stable_key.isnot(None),
            )
            .options(selectinload(ScheduledTask.owner_user))
            .order_by(ScheduledTask.name.asc())
            .limit(limit)
            .offset(offset)
        )
        if status:
            stmt = stmt.where(ScheduledTask.status == status)
        if task_type:
            stmt = stmt.where(ScheduledTask.task_type == task_type)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_tasks_by_ids(
        self,
        *,
        tenant_id: int,
        task_ids: list[int],
        status: ScheduledTaskStatus | None = None,
        task_type: ScheduledTaskType | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ScheduledTask]:
        if not task_ids:
            return []
        stmt = (
            select(ScheduledTask)
            .options(selectinload(ScheduledTask.owner_user))
            .where(
                ScheduledTask.tenant_id == tenant_id,
                ScheduledTask.id.in_(task_ids),
            )
            .order_by(ScheduledTask.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        if status:
            stmt = stmt.where(ScheduledTask.status == status)
        if task_type:
            stmt = stmt.where(ScheduledTask.task_type == task_type)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def claim_due_tasks_with_lease(
        self,
        *,
        owner_instance_id: str,
        lease_ttl_seconds: int,
        limit: int = 10,
    ) -> list[ScheduledTask]:
        """Claim due pending tasks and attach lease ownership metadata."""
        now = datetime.now(UTC)
        lease_expires_at = now + timedelta(seconds=max(lease_ttl_seconds, 1))
        stmt = (
            select(ScheduledTask)
            .where(
                and_(
                    ScheduledTask.status == TASK_STATUS_PENDING,
                    ScheduledTask.next_run_at.is_not(None),
                    ScheduledTask.next_run_at <= now,
                )
            )
            .order_by(ScheduledTask.next_run_at.asc())
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        result = await self.session.execute(stmt)
        tasks = list(result.scalars().all())

        for task in tasks:
            task.status = TASK_STATUS_RUNNING
            task.owner_instance_id = owner_instance_id
            task.heartbeat_at = now
            task.lease_expires_at = lease_expires_at
            task.fencing_token += 1

        await self.session.flush()
        return tasks

    async def recover_expired_running_tasks(self, *, limit: int = 100) -> list[int]:
        """Requeue running tasks whose lease has expired."""
        now = datetime.now(UTC)
        stmt = (
            select(ScheduledTask)
            .where(
                and_(
                    ScheduledTask.status == TASK_STATUS_RUNNING,
                    ScheduledTask.lease_expires_at.is_not(None),
                    ScheduledTask.lease_expires_at <= now,
                )
            )
            .order_by(ScheduledTask.lease_expires_at.asc())
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        result = await self.session.execute(stmt)
        tasks = list(result.scalars().all())

        for task in tasks:
            task.status = TASK_STATUS_PENDING
            task.owner_instance_id = None
            task.heartbeat_at = None
            task.lease_expires_at = None
            task.fencing_token += 1

        await self.session.flush()
        return [task.id for task in tasks]

    async def heartbeat_lease(
        self,
        *,
        task_id: int,
        owner_instance_id: str,
        fencing_token: int,
        lease_ttl_seconds: int,
    ) -> bool:
        """Renew lease if ownership still matches task fencing token."""
        now = datetime.now(UTC)
        lease_expires_at = now + timedelta(seconds=max(lease_ttl_seconds, 1))
        stmt = (
            update(ScheduledTask)
            .where(
                ScheduledTask.id == task_id,
                ScheduledTask.status == TASK_STATUS_RUNNING,
                ScheduledTask.owner_instance_id == owner_instance_id,
                ScheduledTask.fencing_token == fencing_token,
            )
            .values(
                heartbeat_at=now,
                lease_expires_at=lease_expires_at,
                updated_at=now,
            )
        )
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.rowcount > 0

    async def has_execution_ownership(
        self,
        *,
        task_id: int,
        owner_instance_id: str,
        fencing_token: int,
    ) -> bool:
        """Return True if caller still owns execution rights for the task."""
        stmt = select(ScheduledTask.id).where(
            ScheduledTask.id == task_id,
            ScheduledTask.status == TASK_STATUS_RUNNING,
            ScheduledTask.owner_instance_id == owner_instance_id,
            ScheduledTask.fencing_token == fencing_token,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def release_ownership(self, *, task_id: int) -> None:
        """Clear owner/lease metadata after task reaches terminal status."""
        stmt = (
            update(ScheduledTask)
            .where(ScheduledTask.id == task_id)
            .values(
                owner_instance_id=None,
                heartbeat_at=None,
                lease_expires_at=None,
                updated_at=datetime.now(UTC),
            )
        )
        await self.session.execute(stmt)
        await self.session.flush()

    async def set_error_message_for_task_ids(self, *, task_ids: list[int], error_message: str | None) -> None:
        """Batch-set error message for tasks.

        This helper keeps orchestration free from N+1 row loads when applying
        service-level error semantics to many recovered tasks.
        """
        if not task_ids:
            return
        stmt = (
            update(ScheduledTask)
            .where(ScheduledTask.id.in_(task_ids))
            .values(error_message=error_message, updated_at=datetime.now(UTC))
        )
        await self.session.execute(stmt)
        await self.session.flush()

    async def create_run(
        self,
        *,
        task: ScheduledTask,
        orchestration_run_id: str,
        attempt: int = 1,
    ) -> TaskRun:
        """Create a unified TaskRun record for a scheduled task execution."""
        run = TaskRun(
            task_type=task.task_type,
            task_name=task.name,
            status=TASK_RUN_STATUS_RUNNING,
            trigger="scheduled",
            started_at=datetime.now(UTC),
            scheduled_task_id=task.id,
            tenant_id=task.tenant_id,
            orchestration_run_id=orchestration_run_id,
            attempt=attempt,
            result={},
            input_params=task.input_params or {},
        )
        self.session.add(run)
        await self.session.flush()
        await self.session.refresh(run)
        return run

    async def mark_run_success(
        self,
        *,
        run_id: int,
        task_id: int,
        result: dict | None,
        next_run_at: datetime | None,
        task_status: str,
        finished_at: datetime,
        duration_ms: int,
    ) -> None:
        """Persist success state for task run and parent task.

        Service layer provides computed state (status transitions, duration).
        Repository handles entity retrieval and persistence.
        """
        run = await self.session.get(TaskRun, run_id)
        if not run:
            raise ValueError(f"TaskRun {run_id} not found")

        run.status = TASK_RUN_STATUS_SUCCESS
        run.finished_at = finished_at
        run.duration_ms = duration_ms
        run.result = result

        task = await self.session.get(ScheduledTask, task_id)
        if not task:
            raise ValueError(f"ScheduledTask {task_id} not found")

        task.last_run_at = finished_at
        task.next_run_at = next_run_at
        task.error_message = None
        task.status = task_status
        await self.release_ownership(task_id=task_id)
        await self.session.flush()

    async def mark_run_failed(
        self,
        *,
        run_id: int,
        task_id: int,
        error_message: str,
        result: dict | None,
        next_run_at: datetime | None,
        task_status: str,
        finished_at: datetime,
        duration_ms: int,
    ) -> None:
        """Persist failure state for task run and parent task.

        Service layer provides computed state (status transitions, duration, error message).
        Repository handles entity retrieval and persistence.
        """
        run = await self.session.get(TaskRun, run_id)
        if not run:
            raise ValueError(f"TaskRun {run_id} not found")

        run.status = TASK_RUN_STATUS_FAILED
        run.finished_at = finished_at
        run.duration_ms = duration_ms
        run.error_message = error_message
        run.result = result

        task = await self.session.get(ScheduledTask, task_id)
        if not task:
            raise ValueError(f"ScheduledTask {task_id} not found")

        task.last_run_at = finished_at
        task.error_message = error_message
        task.next_run_at = next_run_at
        task.status = task_status
        await self.release_ownership(task_id=task_id)
        await self.session.flush()

    async def list_task_runs(
        self,
        *,
        task_id: int,
        tenant_id: int,
        limit: int = 50,
        offset: int = 0,
    ) -> list[TaskRun]:
        """List unified TaskRun records for a given scheduled task."""
        stmt = (
            select(TaskRun)
            .where(
                TaskRun.scheduled_task_id == task_id,
                TaskRun.tenant_id == tenant_id,
            )
            .order_by(TaskRun.started_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_run_by_id(
        self,
        *,
        run_id: int,
        task_id: int,
        tenant_id: int,
    ) -> TaskRun | None:
        """Get a single TaskRun by ID, scoped to task and tenant."""
        stmt = select(TaskRun).where(
            TaskRun.id == run_id,
            TaskRun.scheduled_task_id == task_id,
            TaskRun.tenant_id == tenant_id,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_task_runs_with_count(
        self,
        *,
        task_id: int,
        tenant_id: int,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[TaskRun], int]:
        """List unified TaskRun records with total count for pagination."""
        # Get total count
        count_stmt = select(func.count(TaskRun.id)).where(
            TaskRun.scheduled_task_id == task_id,
            TaskRun.tenant_id == tenant_id,
        )
        count_result = await self.session.execute(count_stmt)
        total = count_result.scalar_one()

        # Get paginated results
        data_stmt = (
            select(TaskRun)
            .where(
                TaskRun.scheduled_task_id == task_id,
                TaskRun.tenant_id == tenant_id,
            )
            .order_by(TaskRun.started_at.desc())
            .limit(limit)
            .offset(offset)
        )
        data_result = await self.session.execute(data_stmt)
        runs = list(data_result.scalars().all())

        return runs, total

    async def cancel_task(
        self,
        *,
        task_id: int,
        tenant_id: int,
        user_id: int | None = None,
    ) -> bool:
        where_filters = [
            ScheduledTask.id == task_id,
            ScheduledTask.tenant_id == tenant_id,
        ]
        if user_id is not None:
            where_filters.append(ScheduledTask.user_id == user_id)
        stmt = (
            update(ScheduledTask)
            .where(*where_filters)
            .values(status=TASK_STATUS_CANCELLED, next_run_at=None, updated_at=datetime.now(UTC))
        )
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.rowcount > 0

    async def pause_task(
        self,
        *,
        task_id: int,
        tenant_id: int,
        user_id: int | None = None,
    ) -> bool:
        where_filters = [
            ScheduledTask.id == task_id,
            ScheduledTask.tenant_id == tenant_id,
        ]
        if user_id is not None:
            where_filters.append(ScheduledTask.user_id == user_id)
        stmt = (
            update(ScheduledTask).where(*where_filters).values(status=TASK_STATUS_PAUSED, updated_at=datetime.now(UTC))
        )
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.rowcount > 0

    async def resume_task(
        self,
        *,
        task_id: int,
        tenant_id: int,
        next_run_at: datetime | None,
        user_id: int | None = None,
    ) -> bool:
        where_filters = [
            ScheduledTask.id == task_id,
            ScheduledTask.tenant_id == tenant_id,
        ]
        if user_id is not None:
            where_filters.append(ScheduledTask.user_id == user_id)
        stmt = (
            update(ScheduledTask)
            .where(*where_filters)
            .values(status=TASK_STATUS_PENDING, next_run_at=next_run_at, updated_at=datetime.now(UTC))
        )
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.rowcount > 0

    async def trigger_immediate_run(
        self,
        *,
        task_id: int,
        tenant_id: int,
        user_id: int | None = None,
    ) -> bool:
        """Trigger an immediate run by setting next_run_at to now.

        The scheduler will pick up tasks with next_run_at <= now.
        """
        now = datetime.now(UTC)
        where_filters = [
            ScheduledTask.id == task_id,
            ScheduledTask.tenant_id == tenant_id,
        ]
        if user_id is not None:
            where_filters.append(ScheduledTask.user_id == user_id)
        stmt = (
            update(ScheduledTask)
            .where(*where_filters)
            .values(
                status=TASK_STATUS_PENDING,
                next_run_at=now,
                error_message=None,
                updated_at=now,
            )
        )
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.rowcount > 0

    async def delete_task(self, *, task_id: int, tenant_id: int, user_id: int | None = None) -> bool:
        task = await self.get_task_by_id(task_id, tenant_id=tenant_id, user_id=user_id)
        if not task:
            return False
        await self.session.delete(task)
        await self.session.flush()
        return True
