"""Unit tests for trigger_runs history enrichment."""

from datetime import UTC, datetime
from uuid import uuid4

from apps.tenant_app_service.chat.domain import (
    AgentRunDomain,
    AgentRunStatus,
    ThreadMainMessageDomain,
)
from apps.tenant_app_service.chat.history_adapters import (
    enrich_messages_with_trigger_runs,
    group_runs_by_trigger,
    main_timeline_row_to_api_message,
)
from apps.tenant_app_service.chat.schemas import Message


def _run(*, trigger: str, status: str, invoke_index: int = 0) -> AgentRunDomain:
    now = datetime.now(UTC)
    return AgentRunDomain(
        id=str(uuid4()),
        tenant_id=1,
        thread_id="thread-1",
        agent_id=1,
        trigger_message_id=trigger,
        invoke_index=invoke_index,
        status=status,
        session_id=str(uuid4()),
        created_at=now,
        updated_at=now,
    )


def _human(message_id: str) -> Message:
    return Message(
        message_id=message_id,
        role="human",
        content="hi",
        agent_id=1,
        thread_id="thread-1",
    )


def test_enrich_messages_with_trigger_runs():
    human_id = str(uuid4())
    runs = [_run(trigger=human_id, status=AgentRunStatus.CANCELLED)]
    by_trigger = group_runs_by_trigger(runs)
    enriched = enrich_messages_with_trigger_runs([_human(human_id)], by_trigger)
    assert len(enriched) == 1
    assert enriched[0].trigger_runs is not None
    assert len(enriched[0].trigger_runs) == 1
    assert enriched[0].trigger_runs[0].status == AgentRunStatus.CANCELLED


def test_enrich_stamps_agent_run_status_on_promoted_ai():
    now = datetime.now(UTC)
    run_id = str(uuid4())
    human_id = str(uuid4())
    run = _run(trigger=human_id, status=AgentRunStatus.CANCELLED)
    run = AgentRunDomain(**{**run.__dict__, "id": run_id})
    ai_row = ThreadMainMessageDomain(
        id=1,
        message_id=str(uuid4()),
        thread_id="thread-1",
        type="ai",
        content="partial",
        timestamp=now,
        agent_id=1,
        trigger_message_id=human_id,
        agent_run_id=run_id,
        invoke_index=0,
        session_id=run.session_id,
    )
    ai_msg = main_timeline_row_to_api_message(ai_row, thread_id="thread-1", default_agent_id=1)
    by_trigger = group_runs_by_trigger([run])
    enriched = enrich_messages_with_trigger_runs([ai_msg], by_trigger)
    assert enriched[0].message_metadata is not None
    assert enriched[0].message_metadata["agent_run_status"] == AgentRunStatus.CANCELLED
