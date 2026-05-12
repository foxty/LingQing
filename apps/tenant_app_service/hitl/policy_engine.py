"""Policy engine for HITL decision making."""

from apps.tenant_app_service.agents.domain import ToolConfig

from .domain import (
    HITL_ACTION_ALLOW,
    HITL_ACTION_DENY,
    HITL_ACTION_REQUIRE_HITL,
    ApprovalDecision,
)


def evaluate_approval_decision(tool_config: ToolConfig | None) -> ApprovalDecision:
    """Evaluate whether a tool call needs human approval."""
    if not tool_config:
        return ApprovalDecision(action=HITL_ACTION_DENY, reason="tool config missing")

    if tool_config.hitl_mode == "always":
        return ApprovalDecision(action=HITL_ACTION_REQUIRE_HITL, reason="tool requires human approval")

    return ApprovalDecision(action=HITL_ACTION_ALLOW, reason="tool allowed by policy")
