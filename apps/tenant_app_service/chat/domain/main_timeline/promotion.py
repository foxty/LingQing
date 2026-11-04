"""Run-scoped message promotion helpers."""

from __future__ import annotations


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
    return [row for row in run_rows if not (row.type == "ai" and row.message_id == promoted_main_message_id)]
