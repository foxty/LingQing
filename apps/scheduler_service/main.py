"""Standalone Scheduler Service.

Lightweight background task scheduler using APScheduler.
No FastAPI dependency - pure async Python for minimal overhead.

Two infrastructure APScheduler jobs run here:
- Unified task poller: claims due ScheduledTask rows and executes them (every minute)
- System task reconciler: upserts per-tenant system task rows for new tenants (daily)

All business tasks (vector sync, cleanup, asset sync, etc.) are declared in
apps.shared.tasks.system.definitions, materialized per-tenant by the reconciler, and executed
by the poller via task-type executors.

Development:
    uv run python apps/scheduler_service/main.py

Production:
    python apps/scheduler_service/main.py

Environment:
    PYTHONUNBUFFERED=1 (recommended for Docker)
"""

import asyncio
import inspect
import signal
from datetime import UTC, datetime
from time import perf_counter
from typing import Any
from uuid import uuid4

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from apps.config import get_settings
from apps.shared.tasks.domain import TASK_TYPE_AGENT_RUN
from apps.shared.tasks.execution_service import ScheduledTaskExecutionService
from apps.shared.tasks.system.reconciler import reconcile_all
from apps.shared.utils.logger import get_logger
from apps.tenant_app_service.tasks.agent_run_executor import execute_agent_run_task

logger = get_logger(__name__)


async def poll_and_execute_scheduled_tasks(limit: int = 10) -> dict[str, Any]:
    """Poll for due scheduled tasks and execute them."""
    service = ScheduledTaskExecutionService(
        internal_executors={TASK_TYPE_AGENT_RUN: execute_agent_run_task},
    )
    return await service.poll_and_execute(limit=limit)


settings = get_settings()

scheduler = AsyncIOScheduler()
shutdown_event: asyncio.Event | None = None


def tracked_async_wrapper(job_id: str, job_name: str, coro_func, *args, **kwargs):
    """Wrap a job with unified start/end/failure logs for scheduler tracking.

    APScheduler's AsyncIOScheduler expects a callable that returns a coroutine,
    not a callable that needs to be awaited.
    """

    async def wrapper():
        run_id = uuid4().hex[:8]
        started_at = datetime.now(UTC)
        start_ts = perf_counter()
        logger.info(
            "[SCHEDULER][START] job_id=%s job_name=%s run_id=%s started_at=%s",
            job_id,
            job_name,
            run_id,
            started_at.isoformat(),
        )
        try:
            result = coro_func(*args, **kwargs)
            if inspect.isawaitable(result):
                result = await result

            duration_ms = int((perf_counter() - start_ts) * 1000)
            logger.info(
                "[SCHEDULER][END] job_id=%s job_name=%s run_id=%s duration_ms=%s status=success",
                job_id,
                job_name,
                run_id,
                duration_ms,
            )
            return result
        except Exception:
            duration_ms = int((perf_counter() - start_ts) * 1000)
            logger.exception(
                "[SCHEDULER][END] job_id=%s job_name=%s run_id=%s duration_ms=%s status=failed",
                job_id,
                job_name,
                run_id,
                duration_ms,
            )
            raise

    return wrapper


def register_tasks() -> None:
    """Register infrastructure APScheduler jobs.

    Business tasks (vector sync, cleanup, asset sync, etc.) are driven by the
    DB-backed unified task system: declared in apps.shared.tasks.system.definitions,
    materialized
    per-tenant by reconcile_all(), and dispatched every minute by the poller.
    Only the two infrastructure jobs belong here.
    """
    logger.info("Registering infrastructure tasks...")

    # Unified scheduled task poller (every minute)
    scheduler.add_job(
        tracked_async_wrapper(
            "scheduled_task_poll",
            "Scheduled Task Poller",
            poll_and_execute_scheduled_tasks,
        ),
        "interval",
        minutes=1,
        id="scheduled_task_poll",
        name="Scheduled Task Poller",
        max_instances=5,
    )

    # System task reconciler (daily — ensures new tenants get system tasks)
    scheduler.add_job(
        tracked_async_wrapper(
            "system_task_reconciler",
            "System Task Reconciler",
            reconcile_all,
        ),
        "cron",
        hour=0,
        minute=30,
        id="system_task_reconciler",
        name="System Task Reconciler",
        max_instances=1,
    )


def print_startup_info() -> None:
    """Print scheduler startup information."""
    logger.info("=" * 70)
    logger.info("SCHEDULER SERVICE - STARTUP")
    logger.info("=" * 70)
    logger.info(f"Started at: {datetime.now().isoformat()}")
    logger.info(f"Log level: {settings.LOG_LEVEL}")
    logger.info("")
    logger.info("Registered Tasks:")
    for job in scheduler.get_jobs():
        next_run = getattr(job, "next_run_time", None)
        logger.info(f"  📅 {job.name:30} | Next: {next_run}")
    logger.info("=" * 70)


async def handle_shutdown(signum: int, frame) -> None:
    """Handle graceful shutdown."""
    logger.warning(f"Received signal {signum}, shutting down gracefully...")
    if scheduler.running:
        scheduler.shutdown()
    if shutdown_event is not None:
        shutdown_event.set()
    logger.info("✓ Scheduler stopped")


async def main() -> None:
    """Main entry point."""
    logger.info("Starting Scheduler Service")

    # Register signal handlers
    loop = asyncio.get_event_loop()

    def _schedule_shutdown(sig: signal.Signals) -> None:
        asyncio.create_task(handle_shutdown(sig, None))

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _schedule_shutdown, sig)

    try:
        # Reconcile system tasks for all active tenants before starting the poller
        logger.info("Running system task reconciliation...")
        summary = await reconcile_all()
        logger.info("Reconciliation complete: %s", summary)

        # Register and start tasks
        register_tasks()
        print_startup_info()

        scheduler.start()
        logger.info("✓ Scheduler running - press Ctrl+C to stop")

        # Keep running
        global shutdown_event
        shutdown_event = asyncio.Event()
        while True:
            try:
                await asyncio.wait_for(shutdown_event.wait(), timeout=1)
                break
            except TimeoutError:
                pass

    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler terminated by user")
    finally:
        if scheduler.running:
            scheduler.shutdown()
            logger.info("✓ Scheduler cleanup completed")


if __name__ == "__main__":
    asyncio.run(main())
