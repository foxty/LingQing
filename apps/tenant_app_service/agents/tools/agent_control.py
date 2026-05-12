"""Agent control tools for dynamic skill loading and unloading.

Provides tools for agents to manage their own behavior and state.
"""

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from apps.shared.utils.logger import get_logger
from apps.tenant_app_service.agents.context import extract_runtime_context
from apps.tenant_app_service.agents.tools.tool_result import ToolResult

logger = get_logger(__name__)


@tool
async def load_skill(skill_name: str, reason: str, config: RunnableConfig) -> ToolResult:
    """Load one skill so its prompt and tools become available in subsequent turns.

    Args:
        skill_name: Skill to load (must be listed in the agent's skills config).
        reason: Why this skill is needed for current user request.
        config: Runtime configuration (auto-injected by LangGraph)
    """
    runtime = extract_runtime_context(config)
    tenant_info = f"{runtime.user.tenant_name} (ID: {runtime.user.tenant_id})"

    logger.info(
        "[Tenant %s] User %s requesting load_skill '%s' (reason: %s)",
        tenant_info,
        runtime.user.user_id,
        skill_name,
        reason,
    )
    return ToolResult.success(
        f"Loading skill '{skill_name}' to {reason.lower()}. "
        "Its prompt and tools will be merged into the next LLM iteration."
    )


@tool
async def unload_skill(skill_name: str, reason: str, config: RunnableConfig) -> ToolResult:
    """Unload one skill so its prompt and tools are removed in subsequent turns.

    Args:
        skill_name: Skill to unload.
        reason: Why this skill is no longer needed.
        config: Runtime configuration (auto-injected by LangGraph)
    """
    runtime = extract_runtime_context(config)
    tenant_info = f"{runtime.user.tenant_name} (ID: {runtime.user.tenant_id})"

    logger.info(
        "[Tenant %s] User %s requesting unload_skill '%s' (reason: %s)",
        tenant_info,
        runtime.user.user_id,
        skill_name,
        reason,
    )
    return ToolResult.success(
        f"Unloading skill '{skill_name}' because {reason.lower()}. "
        "Its prompt and tools will be removed in the next LLM iteration."
    )
