"""System task reconciler.

Ensures each active tenant has the correct set of per-tenant ScheduledTask
rows for every enabled SystemTaskDefinition. Runs at scheduler startup and
periodically to onboard new tenants automatically.

Reconciliation is idempotent: existing rows are updated to match the
template if schedule or config drifts; missing rows are created; disabled
templates pause the corresponding task.
"""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from typing_extensions import TypedDict

from apps.shared.db.models import ScheduledTask, Tenant, User
from apps.shared.db.session import app_db_session
from apps.shared.tasks.domain import TASK_STATUS_PAUSED, TASK_STATUS_PENDING, SystemTaskConfig
from apps.shared.tasks.scheduling import compute_next_run_at
from apps.shared.tasks.system.definitions import SYSTEM_TASK_DEFINITIONS, SystemTaskDefinition
from apps.shared.utils.logger import get_logger

logger = get_logger(__name__)

SYSTEM_USER_USERNAME = "__system__"


class _SystemTaskReconcileUpdates(TypedDict, total=False):
    task_config: SystemTaskConfig
    schedule_spec: dict[str, Any]
    next_run_at: datetime | None
    input_params: dict[str, Any] | None
    status: str
    updated_at: datetime


async def _get_or_create_system_user(session: AsyncSession, tenant_id: int) -> User:
    """Return the reserved system user for this tenant, creating it if absent."""
    result = await session.execute(
        select(User).where(User.tenant_id == tenant_id, User.username == SYSTEM_USER_USERNAME)
    )
    user = result.scalar_one_or_none()
    if user is not None:
        return user

    user = User(
        tenant_id=tenant_id,
        username=SYSTEM_USER_USERNAME,
        email=None,
        hashed_password="__system__",  # never used for auth
        role="system",
        status="active",
    )
    session.add(user)
    await session.flush()
    await session.refresh(user)
    logger.info("Created __system__ user for tenant_id=%s user_id=%s", tenant_id, user.id)
    return user


async def _upsert_task_for_definition(
    session: AsyncSession,
    definition: SystemTaskDefinition,
    tenant_id: int,
    system_user_id: int,
) -> None:
    """Create or update one ScheduledTask row for a given definition + tenant."""
    result = await session.execute(
        select(ScheduledTask).where(
            ScheduledTask.tenant_id == tenant_id,
            ScheduledTask.stable_key == definition.stable_key,
        )
    )
    existing = result.scalar_one_or_none()

    next_run_at = compute_next_run_at(
        schedule_type="cron",
        schedule_spec=definition.schedule_spec,
    )

    if existing is None:
        # Use typed SystemTaskConfig for type safety
        task_config: SystemTaskConfig = {"handler_ref": definition.handler_ref}
        task = ScheduledTask(
            tenant_id=tenant_id,
            owner_id=system_user_id,
            user_id=system_user_id,
            name=definition.name,
            task_type=definition.task_type,
            task_config=task_config,
            schedule_type="cron",
            schedule_spec=definition.schedule_spec,
            status=TASK_STATUS_PENDING if definition.enabled else TASK_STATUS_PAUSED,
            next_run_at=next_run_at if definition.enabled else None,
            stable_key=definition.stable_key,
            execution_mode=definition.execution_mode,
            input_params=definition.default_input_params,
        )
        session.add(task)
        logger.info(
            "Reconciler: created system task tenant=%s stable_key=%s",
            tenant_id,
            definition.stable_key,
        )
    else:
        # Update mutable fields if they drifted from the definition
        changed = False
        updates: _SystemTaskReconcileUpdates = {}

        # Sync handler_ref in task_config (unified pattern with type safety)
        expected_config: SystemTaskConfig = {"handler_ref": definition.handler_ref}
        if existing.task_config != expected_config:
            updates["task_config"] = expected_config
            changed = True
        if existing.schedule_spec != definition.schedule_spec:
            updates["schedule_spec"] = definition.schedule_spec
            updates["next_run_at"] = next_run_at
            changed = True
        if existing.input_params != definition.default_input_params:
            updates["input_params"] = definition.default_input_params
            changed = True
        # Handle enabled/disabled transitions.
        # Only auto-pause: never auto-resume a paused task, because a paused
        # row may reflect a deliberate admin pause (admin router) rather than
        # a disabled definition. Re-enabling a definition requires a manual
        # admin resume.
        if not definition.enabled and existing.status == TASK_STATUS_PENDING:
            updates["status"] = TASK_STATUS_PAUSED
            updates["next_run_at"] = None
            changed = True
        elif definition.enabled and existing.status == TASK_STATUS_PAUSED:
            logger.info(
                "Reconciler: leaving manually paused system task tenant=%s stable_key=%s",
                tenant_id,
                definition.stable_key,
            )

        if changed:
            updates["updated_at"] = datetime.now(UTC)
            await session.execute(update(ScheduledTask).where(ScheduledTask.id == existing.id).values(**updates))
            logger.info(
                "Reconciler: updated system task tenant=%s stable_key=%s fields=%s",
                tenant_id,
                definition.stable_key,
                list(updates.keys()),
            )


async def reconcile_for_tenant(tenant_id: int, *, session: AsyncSession | None = None) -> int:
    """Upsert all enabled system task definitions for a single tenant.

    When ``session`` is provided, work runs in that transaction (caller commits).
    Use this from tenant provisioning so the tenant row is visible before FK inserts.

    Returns the number of tasks created or updated.
    """
    if session is not None:
        return await _reconcile_for_tenant_in_session(session, tenant_id)

    async with app_db_session() as owned_session:
        return await _reconcile_for_tenant_in_session(owned_session, tenant_id)


async def _reconcile_for_tenant_in_session(session: AsyncSession, tenant_id: int) -> int:
    system_user = await _get_or_create_system_user(session, tenant_id)
    count = 0
    for definition in SYSTEM_TASK_DEFINITIONS:
        await _upsert_task_for_definition(
            session=session,
            definition=definition,
            tenant_id=tenant_id,
            system_user_id=system_user.id,
        )
        count += 1
    return count


async def reconcile_all() -> dict[str, int]:
    """Reconcile system tasks for all active tenants.

    Returns a summary dict: {'tenants': N, 'tasks_processed': M}.
    """
    async with app_db_session() as session:
        result = await session.execute(select(Tenant.id).where(Tenant.status == "active"))
        tenant_ids = list(result.scalars().all())

    total_tasks = 0
    for tenant_id in tenant_ids:
        try:
            n = await reconcile_for_tenant(tenant_id)
            total_tasks += n
        except Exception:
            logger.exception("Reconciler failed for tenant_id=%s", tenant_id)

    logger.info(
        "System task reconciliation complete: tenants=%s tasks_processed=%s",
        len(tenant_ids),
        total_tasks,
    )
    return {"tenants": len(tenant_ids), "tasks_processed": total_tasks}
