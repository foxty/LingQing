"""Repository for TaskRun model."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.db.models import TaskRun


class TaskRunRepository:
    """Repository for task execution history."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        task_type: str,
        task_name: str,
        trigger: str,
        input_params: dict | None = None,
        scheduled_task_id: int | None = None,
        tenant_id: int | None = None,
        orchestration_run_id: str | None = None,
        attempt: int = 1,
    ) -> TaskRun:
        """Create a new task run record (status=pending)."""
        task_run = TaskRun(
            task_type=task_type,
            task_name=task_name,
            status="pending",
            trigger=trigger,
            started_at=datetime.now(UTC),
            input_params=input_params or {},
            result={},
            scheduled_task_id=scheduled_task_id,
            tenant_id=tenant_id,
            orchestration_run_id=orchestration_run_id,
            attempt=attempt,
        )
        self.session.add(task_run)
        await self.session.flush()
        return task_run

    async def update_status(
        self,
        task_run_id: int,
        status: str,
        error_message: str | None = None,
        result: dict | None = None,
    ) -> TaskRun:
        """Update task run status."""
        db_result = await self.session.execute(select(TaskRun).where(TaskRun.id == task_run_id))
        task_run = db_result.scalar_one()

        task_run.status = status
        if error_message:
            task_run.error_message = error_message
        if result:
            task_run.result = result

        if status in ("success", "failed"):
            task_run.finished_at = datetime.now(UTC)
            task_run.duration_ms = int((task_run.finished_at - task_run.started_at).total_seconds() * 1000)

        await self.session.flush()
        return task_run

    async def get_latest(self, task_type: str | None = None, limit: int = 20) -> list[TaskRun]:
        """Get latest task runs."""
        query = select(TaskRun)

        if task_type:
            query = query.where(TaskRun.task_type == task_type)

        query = query.order_by(TaskRun.started_at.desc()).limit(limit)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_running_tasks(self) -> list[TaskRun]:
        """Get all running tasks."""
        result = await self.session.execute(
            select(TaskRun).where(
                TaskRun.status.in_(["pending", "running"]),
            )
        )
        return list(result.scalars().all())
