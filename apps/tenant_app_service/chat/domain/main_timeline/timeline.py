"""Main timeline domain services (pure functions)."""

from __future__ import annotations

from collections.abc import Iterator

from apps.tenant_app_service.chat.domain.main_timeline.message import ThreadMainMessageDomain


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
    return [row for row in rows if row.type == "human" or (row.type == "ai" and row.agent_id == agent_id)]


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
    turn_limit: int | None,
) -> list[ThreadMainMessageDomain]:
    """Last ``turn_limit`` main pairs for this agent. ``None`` keeps every pair."""
    return select_main_pairs_with_watermark(
        rows,
        agent_id=agent_id,
        through_trigger_message_id=None,
        reserve_tail=turn_limit,
    )


def iter_thread_pair_turns(
    rows: list[ThreadMainMessageDomain],
) -> Iterator[list[ThreadMainMessageDomain]]:
    """Yield ``[human, ...ai]`` turns for every agent on a sorted main timeline."""
    i = 0
    n = len(rows)
    while i < n:
        row = rows[i]
        if row.type != "human":
            i += 1
            continue
        human = row
        i += 1
        ais: list[ThreadMainMessageDomain] = []
        while i < n and rows[i].type != "human":
            if rows[i].type == "ai":
                ais.append(rows[i])
            i += 1
        if ais:
            yield [human, *ais]


def _pair_index_for_trigger(
    pair_turns: list[list[ThreadMainMessageDomain]],
    through_trigger_message_id: str | None,
) -> int | None:
    if not through_trigger_message_id:
        return None
    for index, turn in enumerate(pair_turns):
        if turn and turn[0].type == "human" and turn[0].message_id == through_trigger_message_id:
            return index
    return None


def context_pair_turns(
    pair_turns: list[list[ThreadMainMessageDomain]],
    *,
    through_trigger_message_id: str | None,
    reserve_tail: int | None,
) -> list[list[ThreadMainMessageDomain]]:
    """Keep the verbatim tail, plus pairs the watermark has not absorbed yet.

    Pairs at or before ``through_trigger_message_id`` stay out unless they are inside
    the reserved tail. No watermark keeps only that tail. ``reserve_tail is None``
    means no tail cap: every pair, or every pair after the watermark.
    """
    if reserve_tail is not None and reserve_tail <= 0:
        return []
    watermark_idx = _pair_index_for_trigger(pair_turns, through_trigger_message_id)
    if reserve_tail is None:
        if watermark_idx is None:
            return list(pair_turns)
        return [turn for index, turn in enumerate(pair_turns) if index > watermark_idx]
    total = len(pair_turns)
    tail_start = max(0, total - reserve_tail)
    kept: list[list[ThreadMainMessageDomain]] = []
    for index, turn in enumerate(pair_turns):
        in_tail = index >= tail_start
        if watermark_idx is None:
            if in_tail:
                kept.append(turn)
            continue
        if in_tail or index > watermark_idx:
            kept.append(turn)
    return kept


def aged_out_uncovered_turns(
    rows: list[ThreadMainMessageDomain],
    *,
    reserve_tail: int,
    through_trigger_message_id: str | None,
) -> list[list[ThreadMainMessageDomain]]:
    """Completed pairs outside the reserved tail and strictly after the watermark.

    The pair that just finished stays in the tail, so it is not included.
    A watermark that already sits on the last aged-out pair yields an empty delta.
    """
    pair_turns = list(iter_thread_pair_turns(rows))
    total = len(pair_turns)
    tail_start = total if reserve_tail <= 0 else max(0, total - reserve_tail)
    watermark_idx = _pair_index_for_trigger(pair_turns, through_trigger_message_id)
    start = 0 if watermark_idx is None else watermark_idx + 1
    if start >= tail_start:
        return []
    return pair_turns[start:tail_start]


def select_main_pairs_with_watermark(
    rows: list[ThreadMainMessageDomain],
    *,
    agent_id: int,
    through_trigger_message_id: str | None,
    reserve_tail: int | None,
) -> list[ThreadMainMessageDomain]:
    """Agent-scoped main pairs: verbatim tail, plus pairs after the watermark."""
    rows = scope_main_timeline_rows_for_agent(rows, agent_id)
    pair_turns: list[list[ThreadMainMessageDomain]] = []
    for turn in iter_agent_scoped_turns(rows, agent_id):
        if turn[0].type != "human":
            continue
        if not any(row.type == "ai" for row in turn):
            continue
        pair_turns.append(turn)
    kept = context_pair_turns(
        pair_turns,
        through_trigger_message_id=through_trigger_message_id,
        reserve_tail=reserve_tail,
    )
    return [row for turn in kept for row in turn]


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
    return [row for row in rows if not (row.type == "human" and row.message_id == trigger_message_id)]


def filter_main_timeline_for_context_load(
    rows: list[ThreadMainMessageDomain],
    *,
    agent_id: int,
) -> list[ThreadMainMessageDomain]:
    """All qualifying pair turns before turn cap (wrapper around ``select_main_timeline_pairs_for_context``)."""
    return select_main_timeline_pairs_for_context(
        rows,
        agent_id=agent_id,
        turn_limit=None,
    )


