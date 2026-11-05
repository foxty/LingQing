"""Terminal HITL reject run closure (ack persist + promotion; no graph)."""

from __future__ import annotations

from uuid import uuid4

from langchain_core.messages import AIMessage
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.utils.logger import get_logger
from apps.tenant_app_service.chat.application.runs.closure import (
    RunClosureRollup,
    TerminalHitlRejectInput,
    apply_run_closure,
)
from apps.tenant_app_service.chat.domain.agent_run.closure import RunClosureOutcome

logger = get_logger(__name__)


def _agent_run_message_repository(db: AsyncSession):
    from apps.tenant_app_service.chat.infrastructure.persistence import AgentRunMessageRepository

    return AgentRunMessageRepository(db)


def _build_persistence_config(*, tenant_id: int, approval: TerminalHitlRejectInput) -> dict:
    from apps.tenant_app_service.agents.context import (
        create_agent_runtime_context,
        create_agent_runtime_tenant_context,
    )
    from apps.tenant_app_service.agents.domain import AgentUserContext

    tenant_ctx = create_agent_runtime_tenant_context(
        tenant_id=tenant_id,
        tenant_name="",
        config={},
    )
    user_ctx = AgentUserContext(
        user_id=approval.requested_by,
        username="",
        role="user",
        tenant_id=tenant_id,
        tenant_name="",
    )
    runtime_ctx = create_agent_runtime_context(
        tenant_context=tenant_ctx,
        user_context=user_ctx,
        agent_id=approval.agent_id,
        agent_name="",
        thread_id=approval.thread_id,
        session_id=approval.session_id or "",
    )
    return {
        "configurable": {
            "thread_id": approval.thread_id,
            "runtime": runtime_ctx.model_dump(),
        }
    }


async def finalize_terminal_hitl_reject(
    db: AsyncSession,
    tenant_id: int,
    approval: TerminalHitlRejectInput,
) -> str | None:
    """Persist assistant ack when needed, then close the run via ``apply_run_closure``."""
    from apps.tenant_app_service.chat.application.runs.thread_run_service import ThreadRunService

    ai_content = approval.assistant_ack_content

    if not approval.session_id:
        logger.warning(
            "Terminal HITL resolution missing anchor session for proposal_id=%s",
            approval.proposal_id,
        )
        return ai_content

    executor = ThreadRunService(db, tenant_id)
    run = await executor.get_run_by_session_id(approval.session_id)
    if not run:
        logger.warning(
            "Terminal HITL resolution missing agent run for session_id=%s proposal_id=%s",
            approval.session_id,
            approval.proposal_id,
        )
        return ai_content

    run_message_repo = _agent_run_message_repository(db)
    rollup = RunClosureRollup(
        session_id=approval.session_id,
        thread_id=approval.thread_id,
        run_id=run.id,
    )

    for message in await run_message_repo.get_messages_by_session(approval.session_id):
        if message.type == "ai" and message.content == ai_content:
            await apply_run_closure(
                executor,
                run_id=run.id,
                outcome=RunClosureOutcome.TERMINAL_HITL_REJECT,
                rollup=rollup,
            )
            return None

    ai_message = AIMessage(
        id=str(uuid4()),
        content=ai_content,
        additional_kwargs={"session_id": approval.session_id},
    )
    config = _build_persistence_config(tenant_id=tenant_id, approval=approval)
    config["configurable"]["run_id"] = run.id
    from apps.tenant_app_service.agents.ports.run_scope import AgentRunScope
    from apps.tenant_app_service.chat.infrastructure.adapters.agent_run_port_adapter import (
        chat_agent_run_port_for_run,
    )

    scope = AgentRunScope(
        tenant_id=tenant_id,
        thread_id=approval.thread_id,
        run_id=run.id,
        agent_id=approval.agent_id,
    )
    run_port = chat_agent_run_port_for_run(
        tenant_id=tenant_id,
        agent_id=approval.agent_id,
        run_id=run.id,
    )
    await run_port.persist_run_messages(scope, [ai_message], config, deduplicate=True)
    await apply_run_closure(
        executor,
        run_id=run.id,
        outcome=RunClosureOutcome.TERMINAL_HITL_REJECT,
        rollup=rollup,
    )
    return ai_content
