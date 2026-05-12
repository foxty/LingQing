"""Read-time HITL resolution: fresh approval records → LLM-facing tool messages."""

from __future__ import annotations

from langchain_core.messages import BaseMessage, ToolMessage
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.core.exceptions import ResourceNotFoundError
from apps.tenant_app_service.hitl.domain import (
    HITL_PAYLOAD_TYPE_APPROVAL_RESULT,
    HITL_STATUS_APPROVED,
    HITL_STATUS_CANCELLED,
    HITL_STATUS_EXECUTED,
    HITL_STATUS_EXPIRED,
    HITL_STATUS_PENDING,
    HITL_STATUS_REJECTED,
    is_hitl_blocking_status,
)
from apps.tenant_app_service.hitl.utils import (
    build_hitl_gate_tool_content,
    get_hitl_proposal_id,
    is_hitl_approval_request,
)


def build_hitl_hydrated_tool_content(status: str, tool_name: str) -> str:
    """LLM-facing tool result derived from the current approval record."""
    if status == HITL_STATUS_REJECTED:
        return "The tool call was rejected by the user, please skip it."
    if status == HITL_STATUS_EXPIRED:
        return "The tool call approval expired, please skip it unless the user asks again."
    if status == HITL_STATUS_CANCELLED:
        return "The tool call approval was cancelled, please skip it."
    if status == HITL_STATUS_EXECUTED:
        return f"Tool '{tool_name}' was already executed for this approval."
    if status == HITL_STATUS_APPROVED:
        return "The tool call was approved by the user, please re-execute it."
    return build_hitl_gate_tool_content(tool_name)


def build_hydrated_hitl_tool_message(
    message: ToolMessage,
    *,
    status: str,
    proposal_id: str,
    tool_name: str,
) -> ToolMessage:
    """Build an in-memory ToolMessage for the LLM; does not mutate persisted history."""
    action = status if status in {HITL_STATUS_REJECTED, HITL_STATUS_APPROVED} else None
    hitl_payload: dict[str, str] = {
        "type": HITL_PAYLOAD_TYPE_APPROVAL_RESULT,
        "proposal_id": proposal_id,
    }
    if action:
        hitl_payload["action"] = action

    return ToolMessage(
        id=message.id,
        content=build_hitl_hydrated_tool_content(status, tool_name),
        tool_call_id=message.tool_call_id,
        additional_kwargs={
            **(message.additional_kwargs or {}),
            "hitl": hitl_payload,
        },
    )


def normalize_hitl_gate_tool_message(message: ToolMessage, tool_name: str) -> ToolMessage:
    """Ensure pending gate messages use status-neutral persisted wording."""
    neutral = build_hitl_gate_tool_content(tool_name)
    if message.content == neutral:
        return message
    return ToolMessage(
        id=message.id,
        content=neutral,
        tool_call_id=message.tool_call_id,
        additional_kwargs=message.additional_kwargs,
    )


async def lookup_approval_status(
    proposal_id: str,
    *,
    tenant_id: int,
    db: AsyncSession,
) -> str | None:
    """Return the current approval status, or None when the record is missing."""
    from apps.tenant_app_service.hitl.service import HitlApprovalService

    service = HitlApprovalService(tenant_id, db)
    try:
        approval = await service.get_approval(proposal_id)
    except ResourceNotFoundError:
        return None
    return approval.status


async def is_hitl_proposal_blocking(
    proposal_id: str,
    *,
    tenant_id: int,
    db: AsyncSession,
) -> bool:
    """Return True when the approval record still requires user action or resume."""
    status = await lookup_approval_status(proposal_id, tenant_id=tenant_id, db=db)
    if status is None:
        return True
    return is_hitl_blocking_status(status)


async def hydrate_hitl_history_messages(
    messages: list[BaseMessage],
    *,
    tenant_id: int,
    db: AsyncSession,
) -> list[BaseMessage]:
    """Replace stale HITL gate rows using fresh approval records (in-memory only)."""
    from apps.tenant_app_service.hitl.service import HitlApprovalService

    service = HitlApprovalService(tenant_id, db)
    hydrated: list[BaseMessage] = []

    for message in messages:
        if not isinstance(message, ToolMessage) or not is_hitl_approval_request(message):
            hydrated.append(message)
            continue

        proposal_id = get_hitl_proposal_id(message)
        if not proposal_id:
            hydrated.append(message)
            continue

        try:
            approval = await service.get_approval(proposal_id)
        except ResourceNotFoundError:
            hydrated.append(message)
            continue

        tool_name = approval.tool_name or (message.additional_kwargs or {}).get("tool_name") or "tool"
        if approval.status == HITL_STATUS_PENDING:
            hydrated.append(normalize_hitl_gate_tool_message(message, tool_name))
            continue

        if is_hitl_blocking_status(approval.status):
            hydrated.append(message)
            continue

        hydrated.append(
            build_hydrated_hitl_tool_message(
                message,
                status=approval.status,
                proposal_id=proposal_id,
                tool_name=tool_name,
            )
        )

    return hydrated
