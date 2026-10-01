"""Unit tests for system vs user scheduled task authorization split."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest

from apps.shared.core.exceptions import AuthorizationError, ResourceNotFoundError
from apps.shared.db.models import ScheduledTask, Tenant, User
from apps.shared.domain.actor import ActorContext
from apps.shared.tasks.domain import TASK_STATUS_PAUSED, TASK_STATUS_PENDING, TASK_TYPE_AGENT_RUN
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
        source_type="agent",
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
async def test_reconciler_sets_source_type_system(async_db_session, patch_reconciler_db):
    tenant, _user = await _seed_tenant_user(async_db_session)
    await reconcile_for_tenant(tenant.id)

    result = await async_db_session.execute(
        ScheduledTask.__table__.select().where(ScheduledTask.tenant_id == tenant.id)
    )
    tasks = result.fetchall()
    assert tasks
    assert all(row.source_type == "system" for row in tasks)


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
