"""Integration: HITL pause → approve → checkpoint resume → tool echo."""

from __future__ import annotations

from uuid import uuid4

import pytest
import pytest_asyncio
from langchain_core.messages import AIMessage
from sqlalchemy import select

from apps.shared.db.models import Agent, AgentRunMessage, HitlApproval
from apps.shared.schemas.user import UserDTO
from apps.tenant_app_service.agent_pool import get_agent_pool
from apps.tenant_app_service.agents.agent_base import AgentBase
from apps.tenant_app_service.agents.graph_checkpointer import init_langgraph_checkpointer
from apps.tenant_app_service.chat.agent_run_domain import AgentRunStatus
from apps.tenant_app_service.chat.agent_run_repository import AgentRunRepository
from apps.tenant_app_service.chat.main_message_repository import MainMessageRepository
from apps.tenant_app_service.chat.schemas import ChatRequest, SimpleMessage
from apps.tenant_app_service.chat.turn_service import ChatTurnService
from apps.tenant_app_service.hitl.domain import (
    HITL_STATUS_EXECUTED,
    HITL_STATUS_PENDING,
)
from apps.tenant_app_service.hitl.service import HitlApprovalService

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture(autouse=True)
async def _init_memory_checkpointer():
    await init_langgraph_checkpointer()


def _user_dto(*, user_id: int, tenant_id: int, tenant_name: str = "Integration Tenant") -> UserDTO:
    return UserDTO(
        id=user_id,
        username="integ_user",
        role="admin",
        tenant_id=tenant_id,
        tenant_name=tenant_name,
    )


def _hitl_agent_config(*, agent_id: int) -> dict:
    return {
        "agent_id": agent_id,
        "name": "hitl_integration_agent",
        "system_prompt": "You are a test agent.",
        "default_tools": [
            {"name": "hitl_test_echo", "limit": 3, "hitl": {"mode": "always"}},
        ],
    }


@pytest.mark.asyncio
async def test_hitl_pause_approve_resume_executes_tool(pg_async_db_session, sample_tenant_user_thread):
    """Full v2 path: gate interrupt → approve → checkpoint resume → hitl_test_echo result."""
    thread, tenant_id, user_id = sample_tenant_user_thread
    current_user = _user_dto(user_id=user_id, tenant_id=tenant_id)

    agent_row = await pg_async_db_session.get(Agent, thread.agent_id)
    if agent_row is None:
        pg_async_db_session.add(
            Agent(
                id=thread.agent_id,
                tenant_id=tenant_id,
                owner_id=user_id,
                name="Integration Agent",
                description="hitl integration",
                system_prompt="test",
                config={},
            )
        )
        await pg_async_db_session.flush()

    trigger_message_id = str(uuid4())
    session_id = str(uuid4())
    await MainMessageRepository(pg_async_db_session).insert_human(
        message_id=trigger_message_id,
        thread_id=thread.id,
        content="run hitl echo",
    )
    run = await AgentRunRepository(pg_async_db_session).create_run(
        tenant_id=tenant_id,
        thread_id=thread.id,
        agent_id=thread.agent_id,
        trigger_message_id=trigger_message_id,
        invoke_index=0,
        session_id=session_id,
        status=AgentRunStatus.RUNNING,
    )
    await pg_async_db_session.commit()

    from apps.tenant_app_service.agents.domain import (
        AgentRuntimeContext,
        AgentTenantContext,
        AgentUserContext,
    )

    runtime = AgentRuntimeContext(
        tenant=AgentTenantContext(tenant_id=tenant_id, tenant_name="Integration Tenant", config={}),
        user=AgentUserContext(
            user_id=user_id,
            username="integ_user",
            role="admin",
            tenant_id=tenant_id,
            tenant_name="Integration Tenant",
        ),
        agent_id=thread.agent_id,
        agent_name="hitl_integration_agent",
        thread_id=thread.id,
        session_id=session_id,
    )

    llm_calls = 0
    original_llm = AgentBase._llm_call
    pool = get_agent_pool()
    pool._pool.clear()

    async def mock_llm_call(self, state, config):
        nonlocal llm_calls
        llm_calls += 1
        current = list(state.get("messages", []))
        if llm_calls == 1:
            current.append(
                AIMessage(
                    id=str(uuid4()),
                    content="",
                    tool_calls=[
                        {
                            "id": "tc_hitl_echo",
                            "name": "hitl_test_echo",
                            "args": {"text": "integration-flow"},
                        }
                    ],
                )
            )
        else:
            current.append(AIMessage(id=str(uuid4()), content="Finished after HITL tool."))
        return {
            "messages": current,
            "loop_count": state.get("loop_count", 0) + 1,
        }

    AgentBase._llm_call = mock_llm_call
    try:
        compiled = await pool.get_or_create_agent(_hitl_agent_config(agent_id=thread.agent_id))

        graph_config = {
            "configurable": {
                "thread_id": run.id,
                "db_session": pg_async_db_session,
                "runtime": runtime.model_dump(),
                "run_id": run.id,
                "trigger_message_id": trigger_message_id,
                "invoke_index": 0,
            }
        }

        await compiled.ainvoke(
            {"messages": [], "loop_count": 0, "tool_call_counts": {}},
            config=graph_config,
        )

        assert llm_calls == 1, "HITL pause must not invoke a second LLM turn before resume"

        refreshed = await AgentRunRepository(pg_async_db_session).get_run(tenant_id, run.id)
        assert refreshed is not None
        assert refreshed.status == AgentRunStatus.AWAITING_HITL

        pending = await pg_async_db_session.execute(
            select(HitlApproval).where(
                HitlApproval.tenant_id == tenant_id,
                HitlApproval.thread_id == thread.id,
                HitlApproval.status == HITL_STATUS_PENDING,
            )
        )
        approval_row = pending.scalar_one()
        assert approval_row.tool_name == "hitl_test_echo"

        hitl_service = HitlApprovalService(tenant_id, pg_async_db_session)
        await hitl_service.approve(
            proposal_id=approval_row.proposal_id,
            version=approval_row.version,
            user_id=user_id,
        )
        await pg_async_db_session.commit()

        await AgentRunRepository(pg_async_db_session).transition_status(
            run.id,
            expected=AgentRunStatus.AWAITING_HITL,
            new=AgentRunStatus.RUNNING,
        )
        await pg_async_db_session.commit()

        turn = ChatTurnService(tenant_id, pg_async_db_session)
        turn.schedule_session_end = lambda *args, **kwargs: None  # type: ignore[method-assign]

        async def _same_graph(_agent_id: int, _current_user: UserDTO | None):
            return compiled, None

        turn._get_agent_graph = _same_graph  # type: ignore[method-assign]

        payloads: list[str] = []
        async for line in turn.run_hitl_checkpoint_resume_stream(
            request=ChatRequest(
                tenant_id=tenant_id,
                agent_id=thread.agent_id,
                thread_id=thread.id,
                message=SimpleMessage(role="human", content=""),
            ),
            current_user=current_user,
            session_id=session_id,
            agent_id=thread.agent_id,
            agent_name="hitl_integration_agent",
            run_id=run.id,
            trigger_message_id=trigger_message_id,
            invoke_index=0,
            proposal_id=approval_row.proposal_id,
        ):
            payloads.append(line)

        tool_rows = await pg_async_db_session.execute(
            select(AgentRunMessage).where(
                AgentRunMessage.run_id == run.id,
                AgentRunMessage.type == "tool",
            )
        )
        tool_contents = [row.content for row in tool_rows.scalars().all()]
        assert any("HITL_TEST_ECHO" in (content or "") for content in tool_contents)

        final_run = await AgentRunRepository(pg_async_db_session).get_run(tenant_id, run.id)
        assert final_run is not None
        assert final_run.status == AgentRunStatus.COMPLETED

        approved = await hitl_service.get_approval(approval_row.proposal_id)
        assert approved.status == HITL_STATUS_EXECUTED
    finally:
        AgentBase._llm_call = original_llm
        pool._pool.clear()
