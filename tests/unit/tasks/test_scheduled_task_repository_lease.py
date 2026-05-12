"""Tests for scheduled task lease and fencing behavior."""

from datetime import UTC, datetime, timedelta

import pytest

from apps.shared.db.models import ScheduledTask, Tenant, User
from apps.shared.tasks.domain import (
    SCHEDULE_TYPE_CRON,
    TASK_STATUS_PENDING,
    TASK_STATUS_RUNNING,
    TASK_TYPE_AGENT_RUN,
)
from apps.shared.tasks.repository import ScheduledTaskRepository


async def _create_task(async_db_session, *, status: str, next_run_at: datetime | None, lease_expires_at: datetime | None = None):
    tenant = Tenant(name="t-lease", slug="t-lease")
    async_db_session.add(tenant)
    await async_db_session.flush()

    user = User(
        username="u-lease",
        email="u-lease@example.com",
        hashed_password="x",
        role="admin",
        tenant_id=tenant.id,
    )
    async_db_session.add(user)
    await async_db_session.flush()

    task = ScheduledTask(
        tenant_id=tenant.id,
        owner_id=user.id,
        user_id=user.id,
        name="lease-test",
        task_type=TASK_TYPE_AGENT_RUN,
        task_config={"agent_id": 1, "task_description": "x"},
        schedule_type=SCHEDULE_TYPE_CRON,
        schedule_spec={"cron": "* * * * *", "timezone": "UTC"},
        status=status,
        next_run_at=next_run_at,
        lease_expires_at=lease_expires_at,
        fencing_token=0,
    )
    async_db_session.add(task)
    await async_db_session.flush()
    return task


@pytest.mark.asyncio
async def test_claim_due_tasks_with_lease_sets_owner_and_token(async_db_session):
    now = datetime.now(UTC)
    task = await _create_task(
        async_db_session,
        status=TASK_STATUS_PENDING,
        next_run_at=now - timedelta(minutes=1),
    )
    repo = ScheduledTaskRepository(async_db_session)

    claimed = await repo.claim_due_tasks_with_lease(
        owner_instance_id="scheduler-A",
        lease_ttl_seconds=60,
        limit=10,
    )

    assert len(claimed) == 1
    claimed_task = claimed[0]
    assert claimed_task.id == task.id
    assert claimed_task.status == TASK_STATUS_RUNNING
    assert claimed_task.owner_instance_id == "scheduler-A"
    assert claimed_task.heartbeat_at is not None
    assert claimed_task.lease_expires_at is not None
    assert claimed_task.fencing_token == 1


@pytest.mark.asyncio
async def test_heartbeat_lease_requires_matching_owner_and_token(async_db_session):
    now = datetime.now(UTC)
    task = await _create_task(
        async_db_session,
        status=TASK_STATUS_RUNNING,
        next_run_at=now,
        lease_expires_at=now + timedelta(seconds=5),
    )
    task.owner_instance_id = "scheduler-A"
    task.fencing_token = 2
    await async_db_session.flush()

    repo = ScheduledTaskRepository(async_db_session)

    renewed = await repo.heartbeat_lease(
        task_id=task.id,
        owner_instance_id="scheduler-A",
        fencing_token=2,
        lease_ttl_seconds=120,
    )
    assert renewed is True

    rejected = await repo.heartbeat_lease(
        task_id=task.id,
        owner_instance_id="scheduler-A",
        fencing_token=3,
        lease_ttl_seconds=120,
    )
    assert rejected is False


@pytest.mark.asyncio
async def test_recover_expired_running_tasks_requeues_and_bumps_token(async_db_session):
    now = datetime.now(UTC)
    task = await _create_task(
        async_db_session,
        status=TASK_STATUS_RUNNING,
        next_run_at=now - timedelta(minutes=2),
        lease_expires_at=now - timedelta(seconds=1),
    )
    task.owner_instance_id = "scheduler-old"
    task.fencing_token = 5
    await async_db_session.flush()

    repo = ScheduledTaskRepository(async_db_session)
    recovered_ids = await repo.recover_expired_running_tasks(limit=10)

    assert recovered_ids == [task.id]

    refreshed = await repo.get_task_by_id(task.id)
    assert refreshed is not None
    assert refreshed.status == TASK_STATUS_PENDING
    assert refreshed.owner_instance_id is None
    assert refreshed.lease_expires_at is None
    assert refreshed.heartbeat_at is None
    assert refreshed.fencing_token == 6
