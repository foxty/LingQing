"""Domain types for thread main timeline and agent runs."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Final


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

TERMINAL_AGENT_RUN_STATUSES: frozenset[str] = frozenset(
    {
        AgentRunStatus.COMPLETED,
        AgentRunStatus.FAILED,
        AgentRunStatus.CANCELLED,
    }
)


def run_status_allows_session_summary(status: str) -> bool:
    """Whether session-level summarization may run (run will not continue on same session)."""
    return status in TERMINAL_AGENT_RUN_STATUSES


# Orphaned runs (e.g. server reload after human persist) may be repaired after this window.
RUN_STALE_ACTIVE_SECONDS: Final = 900


def is_stale_active_run(
    started_at: datetime | None,
    *,
    stale_after_seconds: int = RUN_STALE_ACTIVE_SECONDS,
    now: datetime | None = None,
) -> bool:
    """True when an ACTIVE run row should be treated as abandoned for repair."""
    if started_at is None:
        return False
    current = now or datetime.now(UTC)
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=UTC)
    return current - started_at > timedelta(seconds=stale_after_seconds)


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


def scope_main_timeline_rows_for_agent(
    rows: list[ThreadMainMessageDomain],
    agent_id: int,
) -> list[ThreadMainMessageDomain]:
    """Keep humans and this agent's promoted AI rows (drop peer agents on main)."""
    return [
        row
        for row in rows
        if row.type == "human" or (row.type == "ai" and row.agent_id == agent_id)
    ]


def _this_agent_ais_until_next_human(
    rows: list[ThreadMainMessageDomain],
    start_index: int,
    agent_id: int,
) -> tuple[list[ThreadMainMessageDomain], int]:
    """Collect this agent's AI rows after ``rows[start_index - 1]`` human until next human."""
    i = start_index
    n = len(rows)
    agent_ais: list[ThreadMainMessageDomain] = []
    while i < n and rows[i].type != "human":
        if rows[i].type == "ai" and rows[i].agent_id == agent_id:
            agent_ais.append(rows[i])
        i += 1
    return agent_ais, i


def _agent_ai_session_covered(
    row: ThreadMainMessageDomain,
    covered_session_ids: frozenset[str],
) -> bool:
    return bool(row.session_id and row.session_id in covered_session_ids)


def iter_agent_scoped_turns(
    rows: list[ThreadMainMessageDomain],
    agent_id: int,
) -> Iterator[list[ThreadMainMessageDomain]]:
    """Yield trigger-anchored turns for one agent on the main timeline.

    Each turn is ``[human]``, ``[human, ...ai]``, or ``[...ai]`` (orphan AI block).
    Expects ``sort_timeline_trigger_anchored`` order; peer agents' AI may appear
    between humans and are skipped when collecting this agent's segment.
    """
    i = 0
    n = len(rows)
    while i < n:
        row = rows[i]
        if row.type == "human":
            human = row
            agent_ais, i = _this_agent_ais_until_next_human(rows, i + 1, agent_id)
            if agent_ais:
                yield [human, *agent_ais]
            else:
                yield [human]
            continue

        if row.type == "ai" and row.agent_id == agent_id:
            orphan_ais: list[ThreadMainMessageDomain] = []
            while i < n and rows[i].type == "ai" and rows[i].agent_id == agent_id:
                orphan_ais.append(rows[i])
                i += 1
            if orphan_ais:
                yield orphan_ais
            continue

        i += 1


def select_main_timeline_pairs_for_context(
    rows: list[ThreadMainMessageDomain],
    *,
    agent_id: int,
    covered_session_ids: frozenset[str],
    turn_limit: int | None,
) -> list[ThreadMainMessageDomain]:
    """Select human+AI pair turns for LLM main-line context.

    Expects ``sort_timeline_trigger_anchored`` order. Keeps only turns that start
    with a human and include at least one promoted AI for ``agent_id``, omitting:

    - human-only rows (no promoted reply for this agent)
    - AI-only blocks (not anchored to a human in timeline order)
    - turns whose session is already in ``covered_session_ids`` (summary XOR pair)

    Then keeps the last ``turn_limit`` pair turns (``None`` = all qualifying pairs).
    The active user message is loaded outside this helper.
    """
    rows = scope_main_timeline_rows_for_agent(rows, agent_id)
    pair_turns: list[list[ThreadMainMessageDomain]] = []
    for turn in iter_agent_scoped_turns(rows, agent_id):
        if turn[0].type != "human":
            continue
        agent_ais = [row for row in turn if row.type == "ai"]
        if not agent_ais:
            continue
        if covered_session_ids and any(
            _agent_ai_session_covered(ai, covered_session_ids) for ai in agent_ais
        ):
            continue
        pair_turns.append(turn)

    if turn_limit is not None:
        if turn_limit <= 0:
            return []
        pair_turns = pair_turns[-turn_limit:]

    return [row for turn in pair_turns for row in turn]


def slice_main_timeline_turns(
    rows: list[ThreadMainMessageDomain],
    *,
    agent_id: int,
    turn_limit: int | None,
) -> list[ThreadMainMessageDomain]:
    """Keep the last K **paired** main-line turns for this agent (see ``select_main_timeline_pairs_for_context``)."""
    return select_main_timeline_pairs_for_context(
        rows,
        agent_id=agent_id,
        covered_session_ids=frozenset(),
        turn_limit=turn_limit,
    )


def exclude_trigger_human_from_main_rows(
    rows: list[ThreadMainMessageDomain],
    *,
    trigger_message_id: str | None,
) -> list[ThreadMainMessageDomain]:
    """Remove the active run's human from history; it is appended after main load."""
    if not trigger_message_id:
        return list(rows)
    return [
        row
        for row in rows
        if not (row.type == "human" and row.message_id == trigger_message_id)
    ]


def filter_main_timeline_for_context_load(
    rows: list[ThreadMainMessageDomain],
    *,
    agent_id: int,
    covered_session_ids: frozenset[str],
) -> list[ThreadMainMessageDomain]:
    """All qualifying pair turns before turn cap (wrapper around ``select_main_timeline_pairs_for_context``)."""
    return select_main_timeline_pairs_for_context(
        rows,
        agent_id=agent_id,
        covered_session_ids=covered_session_ids,
        turn_limit=None,
    )


def find_promotable_final_ai_row(run_rows: list) -> object | None:
    """Last run-scoped AI row with no tool calls (user-visible terminal reply)."""
    for row in reversed(run_rows):
        if getattr(row, "type", None) != "ai":
            continue
        if getattr(row, "tool_calls", None):
            continue
        return row
    return None


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
