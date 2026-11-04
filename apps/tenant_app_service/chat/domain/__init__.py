"""Chat bounded context — domain layer (no I/O, no frameworks).

Subpackages:
- ``agent_run`` — run aggregate, status, policies
- ``main_timeline`` — main-line messages and timeline domain services
- ``thread`` — thread/message/summary entities
- ``ports`` — repository and external interfaces
"""

from apps.tenant_app_service.chat.domain.agent_run import (
    ACTIVE_AGENT_RUN_STATUSES,
    RUN_STALE_ACTIVE_SECONDS,
    TERMINAL_AGENT_RUN_STATUSES,
    AgentRun,
    AgentRunDomain,
    AgentRunState,
    AgentRunStatus,
    is_stale_active_run,
    run_status_allows_thread_rollup,
)
from apps.tenant_app_service.chat.domain.main_timeline import (
    ThreadMainMessageDomain,
    aged_out_uncovered_turns,
    context_pair_turns,
    drop_run_rows_duplicating_promoted_main,
    exclude_trigger_human_from_main_rows,
    filter_main_timeline_for_context_load,
    find_promotable_final_ai_row,
    iter_agent_scoped_turns,
    iter_thread_pair_turns,
    scope_main_timeline_rows_for_agent,
    select_main_pairs_with_watermark,
    select_main_timeline_pairs_for_context,
    slice_main_timeline_turns,
    sort_timeline_trigger_anchored,
)
from apps.tenant_app_service.chat.domain.ports import AgentRunRepositoryPort
from apps.tenant_app_service.chat.domain.thread import (
    MessageDomain,
    ThreadDomain,
    ThreadSummaryDomain,
    extract_tool_call_ids,
    is_tool_chain_resolved,
)

__all__ = [
    "ACTIVE_AGENT_RUN_STATUSES",
    "AgentRun",
    "AgentRunDomain",
    "AgentRunRepositoryPort",
    "AgentRunState",
    "AgentRunStatus",
    "MessageDomain",
    "RUN_STALE_ACTIVE_SECONDS",
    "TERMINAL_AGENT_RUN_STATUSES",
    "ThreadDomain",
    "ThreadMainMessageDomain",
    "ThreadSummaryDomain",
    "aged_out_uncovered_turns",
    "context_pair_turns",
    "drop_run_rows_duplicating_promoted_main",
    "exclude_trigger_human_from_main_rows",
    "extract_tool_call_ids",
    "filter_main_timeline_for_context_load",
    "find_promotable_final_ai_row",
    "is_stale_active_run",
    "is_tool_chain_resolved",
    "iter_agent_scoped_turns",
    "iter_thread_pair_turns",
    "run_status_allows_thread_rollup",
    "scope_main_timeline_rows_for_agent",
    "select_main_pairs_with_watermark",
    "select_main_timeline_pairs_for_context",
    "slice_main_timeline_turns",
    "sort_timeline_trigger_anchored",
]
