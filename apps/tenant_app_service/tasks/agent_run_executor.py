"""Scheduled agent_run task executor."""

from datetime import UTC, datetime

from sqlalchemy import update

from apps.shared.db.models import ScheduledTask
from apps.shared.db.session import app_db_session
from apps.shared.tasks.domain import ScheduledTaskDomain, normalize_agent_run_task_config, parse_agent_run_task_config
from apps.shared.tasks.execution_service import TaskExecutionResult
from apps.shared.utils.logger import get_logger
from apps.tenant_app_service.chat.service import ChatService
from apps.tenant_app_service.slack.scheduled_delivery import (
    SLACK_SCHEDULED_FAILURE_MESSAGE,
    deliver_scheduled_agent_run_to_slack,
)

logger = get_logger(__name__)


async def _persist_origin_thread_id_if_missing(
    session,
    *,
    task: ScheduledTaskDomain,
    origin_thread_id: str,
) -> None:
    task_config = normalize_agent_run_task_config(task.task_config or {})
    if task_config.get("origin_thread_id"):
        return

    task_config["origin_thread_id"] = origin_thread_id
    await session.execute(
        update(ScheduledTask)
        .where(
            ScheduledTask.id == task.id,
            ScheduledTask.tenant_id == task.tenant_id,
        )
        .values(task_config=task_config, updated_at=datetime.now(UTC))
    )
    await session.flush()


async def execute_agent_run_task(task: ScheduledTaskDomain) -> TaskExecutionResult:
    """Execute a scheduled agent_run task via headless chat."""
    try:
        task_config = parse_agent_run_task_config(task.task_config or {})
    except ValueError as exc:
        raise ValueError(f"{exc} for agent_run task {task.id}") from exc

    agent_id = task_config["agent_id"]
    task_description = task_config["task_description"].strip()
    delivery_thread_id = task_config.get("origin_thread_id")

    execution_context = {
        "tenant_id": task.tenant_id,
        "user_id": task.user_id,
        "agent_id": agent_id,
        "task_description": task_description,
        "origin_thread_id": delivery_thread_id,
    }

    try:
        slack_thread_delivered = False
        async with app_db_session() as db_session:
            chat_service = ChatService(task.tenant_id, db_session)
            response = await chat_service.run_headless(
                user_id=task.user_id,
                agent_id=agent_id,
                message=task_description,
                origin_thread_id=delivery_thread_id,
                task_name=task.name,
            )

            content = response.response.content
            execution_thread_id = response.response.thread_id
            execution_context["thread_id"] = execution_thread_id
            execution_context["session_id"] = response.response.session_id
            response_text = content if isinstance(content, str) else str(content)

            if not delivery_thread_id:
                await _persist_origin_thread_id_if_missing(
                    db_session,
                    task=task,
                    origin_thread_id=execution_thread_id,
                )
                delivery_thread_id = execution_thread_id
                execution_context["origin_thread_id"] = delivery_thread_id

            slack_thread_delivered = await deliver_scheduled_agent_run_to_slack(
                tenant_id=task.tenant_id,
                user_id=task.user_id,
                origin_thread_id=delivery_thread_id,
                response_text=response_text,
                db_session=db_session,
            )

        logger.info(
            "Scheduled agent run completed: task_id=%s tenant=%s thread=%s",
            task.id,
            task.tenant_id,
            execution_thread_id,
        )
        return TaskExecutionResult(
            success=True,
            payload={
                "status": "agent_execution_complete",
                "execution_context": execution_context,
                "response_content": response_text,
                "slack_thread_delivered": slack_thread_delivered,
            },
        )
    except Exception as exc:
        logger.exception("Agent run task failed: task_id=%s", task.id)
        slack_thread_delivered = False
        if delivery_thread_id:
            try:
                async with app_db_session() as db_session:
                    slack_thread_delivered = await deliver_scheduled_agent_run_to_slack(
                        tenant_id=task.tenant_id,
                        user_id=task.user_id,
                        origin_thread_id=delivery_thread_id,
                        response_text=SLACK_SCHEDULED_FAILURE_MESSAGE,
                        db_session=db_session,
                    )
            except Exception:
                logger.exception(
                    "Slack scheduled failure delivery failed: task_id=%s tenant=%s",
                    task.id,
                    task.tenant_id,
                )

        return TaskExecutionResult(
            success=False,
            payload={
                "status": "agent_execution_failed",
                "execution_context": execution_context,
                "slack_thread_delivered": slack_thread_delivered,
            },
            error_message=str(exc),
        )
