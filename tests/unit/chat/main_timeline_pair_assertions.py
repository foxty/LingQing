"""Test helpers for main-timeline context pair invariants (not production domain)."""

from __future__ import annotations

from apps.tenant_app_service.chat.agent_run_domain import (
    ThreadMainMessageDomain,
    iter_agent_scoped_turns,
    scope_main_timeline_rows_for_agent,
)


def _agent_ai_session_covered(
    row: ThreadMainMessageDomain,
    covered_session_ids: frozenset[str],
) -> bool:
    return bool(row.session_id and row.session_id in covered_session_ids)


def assert_main_timeline_summary_pairs_consistent(
    original_sorted: list[ThreadMainMessageDomain],
    filtered: list[ThreadMainMessageDomain],
    *,
    agent_id: int,
    covered_session_ids: frozenset[str],
) -> None:
    """Raise AssertionError if summary filtering left orphan human/AI pairs."""
    if not covered_session_ids:
        return

    original_scoped = scope_main_timeline_rows_for_agent(original_sorted, agent_id)
    filtered_ids = {row.message_id for row in filtered}

    for turn in iter_agent_scoped_turns(original_scoped, agent_id):
        agent_ais = [r for r in turn if r.type == "ai"]
        if not agent_ais:
            continue

        for ai in agent_ais:
            if ai.message_id in filtered_ids and _agent_ai_session_covered(ai, covered_session_ids):
                human_id = turn[0].message_id if turn[0].type == "human" else None
                label = f" for human {human_id}" if human_id else ""
                raise AssertionError(f"covered AI {ai.message_id} still in context{label}")

        summarized_turn = any(_agent_ai_session_covered(ai, covered_session_ids) for ai in agent_ais)
        if not summarized_turn:
            continue

        if turn[0].type == "human" and turn[0].message_id in filtered_ids:
            raise AssertionError(f"orphan human {turn[0].message_id} after summarized turn")
        for ai in agent_ais:
            if ai.message_id in filtered_ids:
                human_id = turn[0].message_id if turn[0].type == "human" else None
                raise AssertionError(
                    f"orphan AI {ai.message_id} after summarized turn for {human_id}"
                )
