"""Unit tests for system task reconciler."""

import pytest
from sqlalchemy import func, select

from apps.shared.db.models import ScheduledTask, Tenant, User
from apps.shared.tasks.domain import TASK_STATUS_PENDING, TASK_TYPE_SYSTEM
from apps.shared.tasks.system.definitions import SYSTEM_TASK_DEFINITIONS
from apps.shared.tasks.system.reconciler import SYSTEM_USER_USERNAME, reconcile_for_tenant


class _SessionContext:
    """Reuse the unit-test SQLite session inside reconciler.app_db_session."""

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


@pytest.mark.asyncio
async def test_reconcile_for_tenant_creates_system_tasks(async_db_session, patch_reconciler_db):
    tenant = Tenant(name="Reconciler Test", slug="reconciler_test")
    async_db_session.add(tenant)
    await async_db_session.commit()
    await async_db_session.refresh(tenant)

    count = await reconcile_for_tenant(tenant.id)

    assert count == len(SYSTEM_TASK_DEFINITIONS)

    result = await async_db_session.execute(select(ScheduledTask).where(ScheduledTask.tenant_id == tenant.id))
    tasks = list(result.scalars().all())
    assert len(tasks) == len(SYSTEM_TASK_DEFINITIONS)

    stable_keys = {task.stable_key for task in tasks}
    assert stable_keys == {definition.stable_key for definition in SYSTEM_TASK_DEFINITIONS}
    assert all(task.task_type == TASK_TYPE_SYSTEM for task in tasks)
    assert all(task.status == TASK_STATUS_PENDING for task in tasks)

    system_user_result = await async_db_session.execute(
        select(User).where(User.tenant_id == tenant.id, User.username == SYSTEM_USER_USERNAME)
    )
    assert system_user_result.scalar_one_or_none() is not None


@pytest.mark.asyncio
async def test_reconcile_for_tenant_is_idempotent(async_db_session, patch_reconciler_db):
    tenant = Tenant(name="Reconciler Idempotent", slug="reconciler_idempotent")
    async_db_session.add(tenant)
    await async_db_session.commit()
    await async_db_session.refresh(tenant)

    first_count = await reconcile_for_tenant(tenant.id)
    second_count = await reconcile_for_tenant(tenant.id)

    assert first_count == second_count == len(SYSTEM_TASK_DEFINITIONS)

    count_result = await async_db_session.execute(
        select(func.count()).select_from(ScheduledTask).where(ScheduledTask.tenant_id == tenant.id)
    )
    assert count_result.scalar_one() == len(SYSTEM_TASK_DEFINITIONS)
