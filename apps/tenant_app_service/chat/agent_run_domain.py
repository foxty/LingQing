"""Domain types for thread main timeline and agent runs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class AgentRunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    AWAITING_HITL = "awaiting_hitl"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


ACTIVE_AGENT_RUN_STATUSES: frozenset[str] = frozenset(
    {
        AgentRunStatus.QUEUED,
        AgentRunStatus.RUNNING,
        AgentRunStatus.AWAITING_HITL,
    }
)


@dataclass(frozen=True)
class AgentRunDomain:
    id: str
    tenant_id: int
    thread_id: str
    agent_id: int
    trigger_message_id: str
    invoke_index: int
    status: str
    session_id: str
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None


@dataclass(frozen=True)
class ThreadMainMessageDomain:
    id: int
    message_id: str
    thread_id: str
    type: str
    content: str
    timestamp: datetime
    agent_id: int | None = None
    trigger_message_id: str | None = None
    agent_run_id: str | None = None
    invoke_index: int | None = None
    session_id: str | None = None
    additional_kwargs: dict | None = None
    message_metadata: dict | None = None
    created_at: datetime | None = None


def sort_timeline_trigger_anchored(rows: list[ThreadMainMessageDomain]) -> list[ThreadMainMessageDomain]:
    """Order main rows: humans by send time; AI immediately after their trigger human."""
    humans_by_id: dict[str, ThreadMainMessageDomain] = {}
    ai_rows: list[ThreadMainMessageDomain] = []
    orphan_ai: list[ThreadMainMessageDomain] = []

    for row in rows:
        if row.type == "human":
            humans_by_id[row.message_id] = row
        elif row.type == "ai":
            ai_rows.append(row)
        else:
            orphan_ai.append(row)

    ordered: list[ThreadMainMessageDomain] = []
    sorted_humans = sorted(
        humans_by_id.values(),
        key=lambda m: (m.created_at or m.timestamp, m.id),
    )
    ai_by_trigger: dict[str, list[ThreadMainMessageDomain]] = {}
    for ai in ai_rows:
        trigger = ai.trigger_message_id
        if not trigger:
            orphan_ai.append(ai)
            continue
        ai_by_trigger.setdefault(trigger, []).append(ai)

    for human in sorted_humans:
        ordered.append(human)
        siblings = ai_by_trigger.pop(human.message_id, [])
        siblings.sort(key=lambda m: (m.invoke_index or 0, m.created_at or m.timestamp, m.id))
        ordered.extend(siblings)

    for _trigger_id, siblings in sorted(ai_by_trigger.items(), key=lambda kv: kv[0]):
        siblings.sort(key=lambda m: (m.invoke_index or 0, m.created_at or m.timestamp, m.id))
        ordered.extend(siblings)

    ordered.extend(orphan_ai)
    return ordered


def filter_main_timeline_for_context_load(
    rows: list[ThreadMainMessageDomain],
    *,
    agent_id: int,
    covered_session_ids: frozenset[str],
) -> list[ThreadMainMessageDomain]:
    """Drop main-line AI already represented in thread/session summaries.

    Humans are kept so parallel agent runs on the same trigger still see the user turn.
    Promoted AI rows with a summarized ``session_id`` are omitted to avoid duplicating
    compressed history in the literal tail.
    """
    if not covered_session_ids:
        return list(rows)
    kept: list[ThreadMainMessageDomain] = []
    for row in rows:
        if row.type == "human":
            kept.append(row)
            continue
        if row.type == "ai" and row.agent_id == agent_id:
            if row.session_id and row.session_id in covered_session_ids:
                continue
            kept.append(row)
    return kept


def drop_run_rows_duplicating_promoted_main(
    run_rows: list,
    *,
    promoted_main_message_id: str | None,
) -> list:
    """Remove run AI rows whose ``message_id`` matches promoted main timeline AI."""
    if not promoted_main_message_id:
        return run_rows
    return [
        row
        for row in run_rows
        if not (row.type == "ai" and row.message_id == promoted_main_message_id)
    ]
