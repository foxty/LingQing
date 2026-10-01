"""Unit tests for system vs user scheduled task authorization split."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest

from apps.shared.core.exceptions import AuthorizationError, ResourceNotFoundError
from apps.shared.db.models import ScheduledTask, TaskRun, Tenant, User
from apps.shared.domain.actor import ActorContext
from apps.shared.tasks.domain import (
    TASK_RUN_STATUS_SUCCESS,
    TASK_STATUS_PAUSED,
    TASK_STATUS_PENDING,
    TASK_TYPE_AGENT_RUN,
    TASK_TYPE_SYSTEM,
)
from apps.shared.tasks.service import ScheduledTaskService
from apps.shared.tasks.system.reconciler import reconcile_for_tenant


class _SessionContext:
    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.fixture
def patch_reconciler_db(monkeypatch, async_db_session):
    monkeypatch.setattr(
        "apps.shared.tasks.system.reconciler.app_db_session",
        lambda: _SessionContext(async_db_session),
    )


async def _seed_tenant_user(async_db_session, *, role: str = "member") -> tuple[Tenant, User]:
    tenant = Tenant(name="Auth Split Test", slug="auth_split_test")
    async_db_session.add(tenant)
    await async_db_session.flush()
    user = User(
        tenant_id=tenant.id,
        username="test_user",
        email="test@example.com",
        hashed_password="hash",
        role=role,
        status="active",
    )
    async_db_session.add(user)
    await async_db_session.commit()
    await async_db_session.refresh(tenant)
    await async_db_session.refresh(user)
    return tenant, user


async def _create_user_task(async_db_session, *, tenant_id: int, user_id: int) -> ScheduledTask:
    task = ScheduledTask(
        tenant_id=tenant_id,
        owner_id=user_id,
        user_id=user_id,
        name="User Task",
        task_type=TASK_TYPE_AGENT_RUN,
        task_config={"agent_id": 1, "task_description": "User Task"},
        schedule_type="once",
        schedule_spec={"run_at": datetime.now(UTC).isoformat()},
        status=TASK_STATUS_PENDING,
        next_run_at=datetime.now(UTC),
    )
    async_db_session.add(task)
    await async_db_session.commit()
    await async_db_session.refresh(task)
    return task


def _actor(*, tenant_id: int, user_id: int, role: str) -> ActorContext:
    return ActorContext(tenant_id=tenant_id, user_id=user_id, user_role=role)


@pytest.mark.asyncio
async def test_system_task_hidden_from_user_read_access(async_db_session, patch_reconciler_db):
    tenant, user = await _seed_tenant_user(async_db_session)
    await reconcile_for_tenant(tenant.id)

    result = await async_db_session.execute(
        ScheduledTask.__table__.select().where(
            ScheduledTask.tenant_id == tenant.id,
            ScheduledTask.stable_key.isnot(None),
        )
    )
    system_task_id = result.first().id

    service = ScheduledTaskService.create(tenant_id=tenant.id, db_session=async_db_session)
    actor = _actor(tenant_id=tenant.id, user_id=user.id, role="admin")

    with patch.object(service, "_has_tenant_admin", AsyncMock(return_value=True)):
        with patch.object(service._task_guard(actor), "require_read", AsyncMock()):
            with pytest.raises(ResourceNotFoundError):
                await service.require_read_access(task_id=system_task_id, actor=actor)


@pytest.mark.asyncio
async def test_list_system_tasks_requires_tenant_admin(async_db_session, patch_reconciler_db):
    tenant, user = await _seed_tenant_user(async_db_session)
    await reconcile_for_tenant(tenant.id)

    service = ScheduledTaskService.create(tenant_id=tenant.id, db_session=async_db_session)
    actor = _actor(tenant_id=tenant.id, user_id=user.id, role="member")

    with patch.object(service, "_has_tenant_admin", AsyncMock(return_value=False)):
        with pytest.raises(AuthorizationError):
            await service.list_system_tasks_for_admin(actor=actor)

    with patch.object(service, "_has_tenant_admin", AsyncMock(return_value=True)):
        tasks = await service.list_system_tasks_for_admin(actor=actor)
        assert tasks
        assert all(task.stable_key for task in tasks)


@pytest.mark.asyncio
async def test_user_task_list_excludes_system_tasks(async_db_session, patch_reconciler_db):
    tenant, user = await _seed_tenant_user(async_db_session)
    await reconcile_for_tenant(tenant.id)
    user_task = await _create_user_task(async_db_session, tenant_id=tenant.id, user_id=user.id)

    service = ScheduledTaskService.create(tenant_id=tenant.id, db_session=async_db_session)
    user_only = await service.repo.list_for_tenant(tenant_id=tenant.id, user_tasks_only=True)
    all_tasks = await service.repo.list_for_tenant(tenant_id=tenant.id, user_tasks_only=False)

    assert {task.id for task in user_only} == {user_task.id}
    assert len(all_tasks) > len(user_only)


@pytest.mark.asyncio
async def test_delete_system_task_blocked(async_db_session, patch_reconciler_db):
    tenant, user = await _seed_tenant_user(async_db_session)
    await reconcile_for_tenant(tenant.id)

    result = await async_db_session.execute(
        ScheduledTask.__table__.select().where(
            ScheduledTask.tenant_id == tenant.id,
            ScheduledTask.stable_key.isnot(None),
        )
    )
    system_task_id = result.first().id
    service = ScheduledTaskService.create(tenant_id=tenant.id, db_session=async_db_session)
    actor = _actor(tenant_id=tenant.id, user_id=user.id, role="admin")

    with patch.object(service, "_has_tenant_admin", AsyncMock(return_value=True)):
        with pytest.raises(ResourceNotFoundError):
            await service.delete_task_for_actor(task_id=system_task_id, actor=actor)


@pytest.mark.asyncio
async def test_reconciler_sets_task_type_system(async_db_session, patch_reconciler_db):
    tenant, _user = await _seed_tenant_user(async_db_session)
    await reconcile_for_tenant(tenant.id)

    result = await async_db_session.execute(
        ScheduledTask.__table__.select().where(ScheduledTask.tenant_id == tenant.id)
    )
    tasks = result.fetchall()
    assert tasks
    assert all(row.task_type == TASK_TYPE_SYSTEM for row in tasks)


@pytest.mark.asyncio
async def test_admin_can_pause_system_task(async_db_session, patch_reconciler_db):
    tenant, user = await _seed_tenant_user(async_db_session)
    await reconcile_for_tenant(tenant.id)

    result = await async_db_session.execute(
        ScheduledTask.__table__.select().where(
            ScheduledTask.tenant_id == tenant.id,
            ScheduledTask.stable_key.isnot(None),
        )
    )
    system_task_id = result.first().id
    service = ScheduledTaskService.create(tenant_id=tenant.id, db_session=async_db_session)
    actor = _actor(tenant_id=tenant.id, user_id=user.id, role="admin")

    with patch.object(service, "_has_tenant_admin", AsyncMock(return_value=True)):
        ok = await service.pause_system_task_for_admin(task_id=system_task_id, actor=actor)
        assert ok is True


@pytest.mark.asyncio
async def test_reconciler_respects_admin_pause(async_db_session, patch_reconciler_db):
    """A manually paused system task must stay paused across reconcile cycles."""
    tenant, user = await _seed_tenant_user(async_db_session)
    await reconcile_for_tenant(tenant.id)

    result = await async_db_session.execute(
        ScheduledTask.__table__.select().where(
            ScheduledTask.tenant_id == tenant.id,
            ScheduledTask.stable_key.isnot(None),
        )
    )
    system_task_id = result.first().id
    service = ScheduledTaskService.create(tenant_id=tenant.id, db_session=async_db_session)
    actor = _actor(tenant_id=tenant.id, user_id=user.id, role="admin")

    with patch.object(service, "_has_tenant_admin", AsyncMock(return_value=True)):
        ok = await service.pause_system_task_for_admin(task_id=system_task_id, actor=actor)
        assert ok is True
    await async_db_session.commit()

    await reconcile_for_tenant(tenant.id)

    task = await service.repo.get_task_by_id(system_task_id, tenant_id=tenant.id)
    assert task.status == TASK_STATUS_PAUSED


async def _first_system_task_id(async_db_session, *, tenant_id: int) -> int:
    result = await async_db_session.execute(
        ScheduledTask.__table__.select().where(
            ScheduledTask.tenant_id == tenant_id,
            ScheduledTask.stable_key.isnot(None),
        )
    )
    return result.first().id


@pytest.mark.asyncio
async def test_admin_can_resume_system_task(async_db_session, patch_reconciler_db):
    tenant, user = await _seed_tenant_user(async_db_session)
    await reconcile_for_tenant(tenant.id)
    system_task_id = await _first_system_task_id(async_db_session, tenant_id=tenant.id)

    service = ScheduledTaskService.create(tenant_id=tenant.id, db_session=async_db_session)
    actor = _actor(tenant_id=tenant.id, user_id=user.id, role="admin")

    with patch.object(service, "_has_tenant_admin", AsyncMock(return_value=True)):
        assert await service.pause_system_task_for_admin(task_id=system_task_id, actor=actor) is True
        assert await service.resume_system_task_for_admin(task_id=system_task_id, actor=actor) is True

    task = await service.repo.get_task_by_id(system_task_id, tenant_id=tenant.id)
    assert task.status == TASK_STATUS_PENDING
    assert task.next_run_at is not None


@pytest.mark.asyncio
async def test_admin_can_run_system_task(async_db_session, patch_reconciler_db):
    tenant, user = await _seed_tenant_user(async_db_session)
    await reconcile_for_tenant(tenant.id)
    system_task_id = await _first_system_task_id(async_db_session, tenant_id=tenant.id)

    service = ScheduledTaskService.create(tenant_id=tenant.id, db_session=async_db_session)
    actor = _actor(tenant_id=tenant.id, user_id=user.id, role="admin")

    with patch.object(service, "_has_tenant_admin", AsyncMock(return_value=True)):
        ok = await service.run_system_task_for_admin(task_id=system_task_id, actor=actor)
        assert ok is True


@pytest.mark.asyncio
async def test_list_system_task_runs_for_admin(async_db_session, patch_reconciler_db):
    tenant, user = await _seed_tenant_user(async_db_session)
    await reconcile_for_tenant(tenant.id)
    system_task = await async_db_session.get(
        ScheduledTask,
        await _first_system_task_id(async_db_session, tenant_id=tenant.id),
    )

    run = TaskRun(
        task_type=TASK_TYPE_SYSTEM,
        task_name=system_task.name,
        status=TASK_RUN_STATUS_SUCCESS,
        trigger="scheduled",
        started_at=datetime.now(UTC),
        finished_at=datetime.now(UTC),
        duration_ms=100,
        scheduled_task_id=system_task.id,
        tenant_id=tenant.id,
        result={},
        input_params={},
    )
    async_db_session.add(run)
    await async_db_session.commit()

    service = ScheduledTaskService.create(tenant_id=tenant.id, db_session=async_db_session)
    actor = _actor(tenant_id=tenant.id, user_id=user.id, role="admin")

    with patch.object(service, "_has_tenant_admin", AsyncMock(return_value=True)):
        dtos, pagination = await service.list_system_task_runs_for_admin(
            task_id=system_task.id,
            actor=actor,
            page=1,
            page_size=20,
        )

    assert pagination.total == 1
    assert len(dtos) == 1
    assert dtos[0].id == run.id


@pytest.mark.asyncio
async def test_user_paths_hidden_for_system_tasks(async_db_session, patch_reconciler_db):
    """User-facing service methods must not reach system tasks (stable_key set)."""
    tenant, user = await _seed_tenant_user(async_db_session)
    await reconcile_for_tenant(tenant.id)
    system_task_id = await _first_system_task_id(async_db_session, tenant_id=tenant.id)

    service = ScheduledTaskService.create(tenant_id=tenant.id, db_session=async_db_session)
    actor = _actor(tenant_id=tenant.id, user_id=user.id, role="admin")

    with patch.object(service, "_has_tenant_admin", AsyncMock(return_value=True)):
        with pytest.raises(ResourceNotFoundError):
            await service.update_task_for_actor(
                task_id=system_task_id,
                actor=actor,
                task_description="blocked",
            )
        with pytest.raises(ResourceNotFoundError):
            await service.cancel_task_for_actor(task_id=system_task_id, actor=actor)
        with pytest.raises(ResourceNotFoundError):
            await service.pause_task_for_actor(task_id=system_task_id, actor=actor)
        with pytest.raises(ResourceNotFoundError):
            await service.resume_task_for_actor(task_id=system_task_id, actor=actor)
        with pytest.raises(ResourceNotFoundError):
            await service.run_task_for_actor(task_id=system_task_id, actor=actor)
        with pytest.raises(ResourceNotFoundError):
            await service.list_task_runs_for_actor(task_id=system_task_id, actor=actor)
        with pytest.raises(ResourceNotFoundError):
            await service.get_run_for_actor(task_id=system_task_id, run_id=1, actor=actor)
