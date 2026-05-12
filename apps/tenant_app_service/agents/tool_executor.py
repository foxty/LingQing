"""Tool execution for agents.

This module handles all tool-related operations:
- Single tool execution with tracking
- Session-scoped caching for read-only tools
- Batch tool execution
- Tool limits enforcement
- Error handling
"""

import json
from datetime import UTC, datetime
from uuid import uuid4

from langchain_core.messages import ToolMessage
from langchain_core.runnables import RunnableConfig

from apps.shared.utils.logger import get_logger
from apps.tenant_app_service.agents.agent_config import AgentConfig
from apps.tenant_app_service.agents.context import extract_runtime_context
from apps.tenant_app_service.agents.domain import ToolCache, ToolCallCounts, ToolExecResult
from apps.tenant_app_service.agents.metrics import tool_call_tracker
from apps.tenant_app_service.agents.tools import ToolError, ToolResult, ToolResultStatus
from apps.tenant_app_service.hitl.domain import (
    HITL_ACTION_REQUIRE_HITL,
    HITL_PAYLOAD_TYPE_APPROVAL_REQUEST,
    HITL_PAYLOAD_TYPE_APPROVAL_RESULT,
    HITL_STATUS_APPROVED,
    HITL_STATUS_EXECUTED,
    HITL_STATUS_REJECTED,
)
from apps.tenant_app_service.hitl.policy_engine import evaluate_approval_decision
from apps.tenant_app_service.hitl.service import HitlApprovalService
from apps.tenant_app_service.hitl.utils import build_hitl_gate_tool_content


def _build_cache_key(tool_name: str, tool_args: dict) -> str:
    """Build a deterministic cache key from tool name and args."""
    sorted_args = json.dumps(tool_args, sort_keys=True, default=str)
    return f"{tool_name}::{sorted_args}"


def _invalidate_cache(tool_cache: dict, invalidate_tools: list[str]) -> dict:
    """Remove cache entries for the given tool names."""
    if not invalidate_tools:
        return tool_cache
    return {k: v for k, v in tool_cache.items() if not any(k.startswith(f"{t}::") for t in invalidate_tools)}


class ToolExecutor:
    """Handles tool execution for agents.

    Responsibilities:
    - Execute individual tool calls with tracking
    - Enforce tool call limits
    - Handle tool execution errors
    - Track tool usage statistics
    """

    def __init__(
        self,
        agent_config: AgentConfig,
        agent_name: str,
    ):
        """Initialize tool executor.

        Args:
            agent_config: Bound agent config for tool limits and skill-aware lookup
            agent_name: Agent name for logging
        """
        self.agent_config = agent_config
        self.logger = get_logger(__name__, agent_name)

    @staticmethod
    def _normalize_observation_to_tool_result(observation: object) -> ToolResult:
        """Normalize raw tool output into ToolResult.

        Contract is strict: all tools must return ToolResult.
        """
        if isinstance(observation, ToolResult):
            return observation

        raise TypeError(f"Invalid tool return contract: expected ToolResult, got {type(observation).__name__}.")

    @staticmethod
    def _increment_tool_count(tool_call_counts: dict, tool_name: str, current_count: int) -> dict:
        updated_counts = tool_call_counts.copy()
        updated_counts[tool_name] = current_count + 1
        return updated_counts

    @staticmethod
    def _build_failure_message(tool_name: str, reason: str) -> str:
        return f"Tool call failed for '{tool_name}': {reason}"

    async def _rollback_runtime_session(self, config: RunnableConfig, tool_name: str) -> None:
        """Rollback runtime db session after tool failure to recover transaction state."""
        db_session = config.get("configurable", {}).get("db_session")
        rollback = getattr(db_session, "rollback", None)
        if not callable(rollback):
            return
        try:
            await rollback()
            self.logger.warning("Rolled back runtime db session after failed tool call: %s", tool_name)
        except Exception:
            self.logger.exception("Failed to rollback runtime db session after tool failure: %s", tool_name)

    async def _handle_hitl_gate(
        self,
        *,
        runtime,
        config: RunnableConfig,
        approval_service: HitlApprovalService,
        risk_level: str,
        tool_name: str,
        tool_call_id: str,
        tool_args: dict,
        additional_kwargs: dict,
    ) -> tuple[ToolMessage | None, str | None]:
        # On resume, use the known proposal_id from configurable directly.
        # This avoids arg-hash drift if the LLM regenerates tool args with minor differences.
        hitl_resume = config.get("configurable", {}).get("hitl_resume") or {}
        proposal_id = hitl_resume.get("proposal_id") or approval_service.build_proposal_id(
            thread_id=runtime.thread_id,
            session_id=runtime.session_id,
            tool_name=tool_name,
            tool_args=tool_args,
        )
        approval = await approval_service.get_or_create_pending(
            tenant_id=runtime.user.tenant_id,
            thread_id=runtime.thread_id,
            session_id=runtime.session_id,
            agent_id=runtime.agent_id,
            proposal_id=proposal_id,
            tool_name=tool_name,
            tool_args=tool_args,
            risk_level=risk_level,
            requested_by=runtime.user.user_id,
        )

        if approval.status == HITL_STATUS_APPROVED:
            self.logger.info("HITL approved, executing tool: %s (%s)", tool_name, proposal_id)
            return None, proposal_id

        if approval.status == HITL_STATUS_EXECUTED:
            return (
                ToolMessage(
                    id=str(uuid4()),
                    content=f"Tool '{tool_name}' already executed for approved proposal.",
                    tool_call_id=tool_call_id,
                    additional_kwargs={
                        **additional_kwargs,
                        "hitl": {
                            "type": HITL_PAYLOAD_TYPE_APPROVAL_RESULT,
                            "proposal_id": proposal_id,
                        },
                    },
                ),
                proposal_id,
            )

        if approval.status == HITL_STATUS_REJECTED:
            return (
                ToolMessage(
                    id=str(uuid4()),
                    content=f"Tool '{tool_name}' was rejected by approver.",
                    tool_call_id=tool_call_id,
                    additional_kwargs={
                        **additional_kwargs,
                        "hitl": {
                            "type": HITL_PAYLOAD_TYPE_APPROVAL_RESULT,
                            "proposal_id": proposal_id,
                        },
                    },
                ),
                proposal_id,
            )

        return (
            ToolMessage(
                id=str(uuid4()),
                content=build_hitl_gate_tool_content(tool_name),
                tool_call_id=tool_call_id,
                additional_kwargs={
                    **additional_kwargs,
                    "hitl": {
                        "type": HITL_PAYLOAD_TYPE_APPROVAL_REQUEST,
                        "proposal_id": proposal_id,
                    },
                },
            ),
            proposal_id,
        )

    async def execute_single_tool(
        self,
        call: dict,
        tool_call_counts: ToolCallCounts,
        config: RunnableConfig,
        loaded_skills: list[str] | None = None,
        tool_cache: ToolCache | None = None,
    ) -> ToolExecResult:
        """Execute a single tool call with tracking, caching, and error handling."""
        if tool_cache is None:
            tool_cache = {}

        runtime = extract_runtime_context(config)
        tool_name = call["name"]
        tool_call_id = call["id"]
        tool_args = call.get("args", {})
        current_count = tool_call_counts.get(tool_name, 0)

        additional_kwargs = {
            "timestamp": datetime.now(UTC).isoformat(),
            "tool_name": tool_name,
        }

        tool_config = self.agent_config.get_tool_config(loaded_skills or [], tool_name, runtime)

        if tool_config:
            additional_kwargs["result_retention"] = tool_config.result_retention

        if not tool_config or not tool_config.tool:
            reason = "tool not available in current mode"
            error_msg = self._build_failure_message(tool_name, reason)
            self.logger.warning(error_msg)
            updated_counts = self._increment_tool_count(tool_call_counts, tool_name, current_count)
            return ToolExecResult(
                ToolMessage(
                    id=str(uuid4()),
                    content=error_msg,
                    tool_call_id=tool_call_id,
                    additional_kwargs={
                        **additional_kwargs,
                        "tool_error": ToolError(
                            code="TOOL_NOT_AVAILABLE",
                            message=reason,
                            retryable=False,
                        ).to_dict(),
                    },
                ),
                updated_counts,
                tool_cache,
            )

        db_session = config.get("configurable", {}).get("db_session")
        approval_service = HitlApprovalService(runtime.user.tenant_id, db_session)
        decision = evaluate_approval_decision(tool_config)
        self.logger.info("Tool '%s' approval decision: %s (reason: %s)", tool_name, decision.action, decision.reason)
        proposal_id: str | None = None

        if decision.action == HITL_ACTION_REQUIRE_HITL:
            hitl_message, proposal_id = await self._handle_hitl_gate(
                runtime=runtime,
                config=config,
                approval_service=approval_service,
                risk_level=decision.risk_level,
                tool_name=tool_name,
                tool_call_id=tool_call_id,
                tool_args=tool_args,
                additional_kwargs=additional_kwargs,
            )
            if hitl_message is not None:
                return ToolExecResult(hitl_message, tool_call_counts, tool_cache)

        # Check if tool has exceeded its limit
        if current_count >= tool_config.limit:
            warning_msg = (
                f"Tool '{tool_name}' has been called {current_count} times (limit: {tool_config.limit}). "
                f"Skipping this call. Please use the information already gathered."
            )
            self.logger.warning(warning_msg)
            return ToolExecResult(
                ToolMessage(
                    id=str(uuid4()),
                    content=warning_msg,
                    tool_call_id=tool_call_id,
                    additional_kwargs=additional_kwargs,
                ),
                tool_call_counts,
                tool_cache,
            )

        # Check cache for cacheable tools
        cache_key = _build_cache_key(tool_name, tool_args) if tool_config.cacheable else None
        if cache_key and cache_key in tool_cache:
            self.logger.debug(f"Cache hit for tool: {tool_name}")
            cached_content = tool_cache[cache_key]
            updated_counts = self._increment_tool_count(tool_call_counts, tool_name, current_count)
            return ToolExecResult(
                ToolMessage(
                    id=str(uuid4()),
                    content=cached_content,
                    tool_call_id=tool_call_id,
                    additional_kwargs={**additional_kwargs, "cached": True},
                ),
                updated_counts,
                tool_cache,
            )

        # Invalidate cache entries declared by this tool
        tool_cache = _invalidate_cache(tool_cache, tool_config.cache_invalidates)

        try:
            self.logger.debug(f"Executing tool: {tool_name} (call #{current_count + 1})")
            if decision.action == HITL_ACTION_REQUIRE_HITL and proposal_id:
                async with approval_service.execution_state_manager(proposal_id):
                    async with tool_call_tracker(tool_name, tool_call_id, tool_args, runtime) as tracker:
                        observation = await tool_config.tool.ainvoke(tool_args, config=config)
                        normalized_result = self._normalize_observation_to_tool_result(observation)
                        if normalized_result.status == ToolResultStatus.ERROR:
                            tracker.record_error(RuntimeError(normalized_result.content))
                        else:
                            tracker.record_result(normalized_result)
            else:
                async with tool_call_tracker(tool_name, tool_call_id, tool_args, runtime) as tracker:
                    observation = await tool_config.tool.ainvoke(tool_args, config=config)
                    normalized_result = self._normalize_observation_to_tool_result(observation)
                    if normalized_result.status == ToolResultStatus.ERROR:
                        tracker.record_error(RuntimeError(normalized_result.content))
                    else:
                        tracker.record_result(normalized_result)

            content = normalized_result.content
            additional_kwargs = {**additional_kwargs, **normalized_result.metadata}
            if normalized_result.status == ToolResultStatus.ERROR:
                reason = normalized_result.content
                if normalized_result.error is not None:
                    additional_kwargs["tool_error"] = normalized_result.error.to_dict()
                    reason = normalized_result.error.message
                else:
                    additional_kwargs["tool_error"] = ToolError(
                        code="TOOL_EXECUTION_ERROR",
                        message=reason,
                        retryable=False,
                    ).to_dict()
                await self._rollback_runtime_session(config, tool_name)
                content = self._build_failure_message(tool_name, reason)
            elif cache_key:
                tool_cache[cache_key] = content

            updated_counts = self._increment_tool_count(tool_call_counts, tool_name, current_count)

            return ToolExecResult(
                ToolMessage(
                    id=str(uuid4()),
                    content=content,
                    tool_call_id=tool_call_id,
                    additional_kwargs=additional_kwargs,
                ),
                updated_counts,
                tool_cache,
            )
        except Exception as e:
            reason = str(e)
            error_msg = self._build_failure_message(tool_name, reason)
            self.logger.error(error_msg, exc_info=True)
            await self._rollback_runtime_session(config, tool_name)
            updated_counts = self._increment_tool_count(tool_call_counts, tool_name, current_count)
            return ToolExecResult(
                ToolMessage(
                    id=str(uuid4()),
                    content=error_msg,
                    tool_call_id=tool_call_id,
                    additional_kwargs={
                        **additional_kwargs,
                        "tool_error": ToolError(
                            code="TOOL_EXECUTION_EXCEPTION",
                            message=reason,
                            retryable=False,
                        ).to_dict(),
                    },
                ),
                updated_counts,
                tool_cache,
            )
