"""Turn admission: per-thread concurrency (Postgres advisory lock + busy gate).

**Layer:** Infrastructure helper used inside prepare transactions — not HTTP application flow.
**Callers:** ``ChatTurnService.prepare_*`` via ``guard_thread_turn_start``.
"""

from __future__ import annotations

import zlib

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.core.exceptions import ThreadBusyError
from apps.tenant_app_service.chat.agent_run_domain import ACTIVE_AGENT_RUN_STATUSES
from apps.tenant_app_service.chat.thread_run_service import ThreadRunService


def thread_advisory_lock_keys(tenant_id: int, thread_id: str) -> tuple[int, int]:
    """Stable two-key advisory lock identity for (tenant, thread)."""
    thread_hash = zlib.crc32(thread_id.encode("utf-8")) & 0x7FFFFFFF
    return tenant_id & 0x7FFFFFFF, thread_hash


async def try_acquire_thread_turn_xact_lock(
    db: AsyncSession,
    *,
    tenant_id: int,
    thread_id: str,
) -> None:
    """Take a transaction-scoped advisory lock; fail fast if another turn is starting."""
    key1, key2 = thread_advisory_lock_keys(tenant_id, thread_id)
    result = await db.execute(
        text("SELECT pg_try_advisory_xact_lock(:key1, :key2)"),
        {"key1": key1, "key2": key2},
    )
    acquired = result.scalar_one()
    if not acquired:
        raise ThreadBusyError(
            "An agent run is already in progress for this thread. Wait for it to finish, then try again.",
            details={"code": "THREAD_BUSY", "reason": "advisory_lock_not_acquired"},
        )


async def assert_thread_accepts_new_user_turn(
    db: AsyncSession,
    *,
    tenant_id: int,
    thread_id: str,
    agent_id: int,
) -> None:
    """Raise when the thread already has an active agent run."""
    snapshot = await ThreadRunService(db, tenant_id).get_active_run(
        thread_id=thread_id,
        agent_id=agent_id,
        repair=True,
    )
    if not snapshot.run_status or snapshot.run_status not in ACTIVE_AGENT_RUN_STATUSES:
        return
    raise ThreadBusyError(
        "An agent run is already in progress for this thread. Wait for it to finish, then try again.",
        details={
            "code": "THREAD_BUSY",
            "reason": "active_agent_run",
            "run_id": snapshot.run_id,
            "run_status": snapshot.run_status,
            "session_id": snapshot.session_id,
        },
    )


async def guard_thread_turn_start(
    db: AsyncSession,
    *,
    tenant_id: int,
    thread_id: str,
    agent_id: int,
    skip_busy_check: bool,
) -> None:
    """Acquire turn-start lock and optionally reject when the thread is busy."""
    await try_acquire_thread_turn_xact_lock(db, tenant_id=tenant_id, thread_id=thread_id)
    if skip_busy_check:
        return
    await assert_thread_accepts_new_user_turn(
        db,
        tenant_id=tenant_id,
        thread_id=thread_id,
        agent_id=agent_id,
    )
