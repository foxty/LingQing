"""Process-local map of agent run_id → asyncio.Task for best-effort stream abort."""

from __future__ import annotations

import asyncio
from typing import Final

from apps.shared.utils.logger import get_logger

logger = get_logger(__name__)

_TASKS: Final[dict[str, asyncio.Task]] = {}


def register(run_id: str, task: asyncio.Task) -> None:
    if run_id in _TASKS and _TASKS[run_id] is not task:
        logger.warning("Overwriting execution registry entry for run_id=%s", run_id)
    _TASKS[run_id] = task


def unregister(run_id: str) -> None:
    _TASKS.pop(run_id, None)


def cancel_local(run_id: str) -> bool:
    """Cancel the in-process task for this run, if registered. Returns True when cancel was sent."""
    task = _TASKS.get(run_id)
    if task is None or task.done():
        return False
    task.cancel()
    return True


def cancel_all_registered() -> None:
    """Best-effort cancel on app shutdown."""
    for run_id, task in list(_TASKS.items()):
        if not task.done():
            task.cancel()
            logger.info("Cancelled registered agent run task on shutdown run_id=%s", run_id)
    _TASKS.clear()
