"""Tool-call chain resolution (domain helpers)."""

from __future__ import annotations

from typing import Any


def extract_tool_call_ids(tool_calls: list[dict[str, Any]] | None) -> list[str]:
    if not tool_calls:
        return []
    return [tool_call_id for tc in tool_calls if isinstance(tc, dict) and (tool_call_id := tc.get("id"))]


def is_tool_chain_resolved(
    tool_call_ids: list[str],
    resolved_tool_call_ids: set[str],
    has_final_ai_after_tools: bool,
) -> bool:
    if not tool_call_ids:
        return False
    if not resolved_tool_call_ids.issuperset(tool_call_ids):
        return False
    return has_final_ai_after_tools
