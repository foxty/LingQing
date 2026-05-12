"""RBAC for agent tools: same rules as ``require_permission`` in the HTTP layer.

Agent tools are not FastAPI routes, so they cannot use ``Depends(require_permission)``.
Use ``tool_rbac_denied`` inside ``agent_tool_db_session`` after resolving runtime.

A decorator is a poor fit here: tools open their own DB session in the body, and
``@tool`` must wrap the callable LangChain invokes; composing decorators with session
scope is error-prone.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.authz.ta_rbac import role_has_permission
from apps.tenant_app_service.agents.tools.tool_result import ToolResult


async def tool_rbac_denied(
    db: AsyncSession,
    tenant_id: int,
    role: str,
    *permissions: str,
    denied_message: str = "Insufficient permissions for this action",
) -> ToolResult | None:
    """If the role lacks all listed permissions, return an error ``ToolResult``.

    If any permission matches (same OR semantics as ``require_permission``), returns ``None``.
    """
    if not permissions:
        raise ValueError("tool_rbac_denied requires at least one permission")
    for perm in permissions:
        if await role_has_permission(db, tenant_id, role, perm):
            return None
    return ToolResult.error_result(denied_message, code="PERMISSION_DENIED")
