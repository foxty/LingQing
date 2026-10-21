"""Resolve which roster agent should handle a turn from message text."""

from __future__ import annotations

from typing import Protocol


class RosterAgentEntry(Protocol):
    agent_id: int
    display_alias: str | None


def resolve_agent_id_from_roster(
    *,
    roster: list[RosterAgentEntry],
    endpoint_agent_id: int,
    message_text: str,
) -> int | None:
    if not roster:
        return endpoint_agent_id
    if len(roster) == 1:
        return roster[0].agent_id
    lowered = message_text.lower()
    matches: list[int] = []
    for entry in roster:
        alias = (entry.display_alias or "").strip()
        if alias and alias.lower() in lowered:
            matches.append(entry.agent_id)
    if len(matches) == 1:
        return matches[0]
    return None
