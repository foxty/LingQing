"""Pure helpers for inspecting persisted HITL tool-message shape (no DB I/O).

For read-time resolution from approval records, see hitl.history.
"""

from typing import Any, Dict, Union

from langchain_core.messages import ToolMessage

from apps.tenant_app_service.hitl.domain import (
    HITL_PAYLOAD_TYPE_APPROVAL_REQUEST,
    HITL_PAYLOAD_TYPE_APPROVAL_RESULT,
)


def get_hitl_payload(message: Union[ToolMessage, Any]) -> Dict[str, Any] | None:
    """Safely extract HITL payload from a message or message-like object.

    Accepts ToolMessage or any object with additional_kwargs attribute.

    Args:
        message: ToolMessage or object with additional_kwargs

    Returns:
        HITL payload dict if exists and valid, None otherwise
    """
    additional_kwargs = getattr(message, "additional_kwargs", None)
    if not isinstance(additional_kwargs, dict):
        return None

    payload = additional_kwargs.get("hitl")
    if isinstance(payload, dict):
        return payload
    return None


def has_hitl_payload(message: Union[ToolMessage, Any]) -> bool:
    """Check if message has any HITL payload.

    Accepts ToolMessage or any object with additional_kwargs attribute.

    Args:
        message: ToolMessage or object with additional_kwargs

    Returns:
        True if message has valid HITL payload
    """
    return get_hitl_payload(message) is not None


def is_hitl_approval_request(message: Union[ToolMessage, Any], proposal_id: str | None = None) -> bool:
    """Check if message is a HITL approval request, optionally for specific proposal.

    Accepts ToolMessage or any object with additional_kwargs attribute.

    Args:
        message: ToolMessage or object with additional_kwargs
        proposal_id: Optional proposal ID to match

    Returns:
        True if message is an approval request (and matches proposal_id if provided)
    """
    payload = get_hitl_payload(message)
    if not payload:
        return False

    if payload.get("type") != HITL_PAYLOAD_TYPE_APPROVAL_REQUEST:
        return False

    if proposal_id is not None:
        return payload.get("proposal_id") == proposal_id

    return True


def is_hitl_approval_result(message: Union[ToolMessage, Any], proposal_id: str | None = None) -> bool:
    """Check if message is a HITL approval result, optionally for specific proposal.

    Accepts ToolMessage or any object with additional_kwargs attribute.

    Args:
        message: ToolMessage or object with additional_kwargs
        proposal_id: Optional proposal ID to match

    Returns:
        True if message is an approval result (and matches proposal_id if provided)
    """
    payload = get_hitl_payload(message)
    if not payload:
        return False

    if payload.get("type") != HITL_PAYLOAD_TYPE_APPROVAL_RESULT:
        return False

    if proposal_id is not None:
        return payload.get("proposal_id") == proposal_id

    return True


HITL_SKIPPED_TOOL_CONTENT: str = "Skipped: Waiting for HITL approval"


def build_hitl_gate_tool_content(tool_name: str) -> str:
    """Status-neutral persisted content when a tool call is gated by HITL."""
    return f"Tool '{tool_name}' requires human approval."


def get_hitl_proposal_id(message: Union[ToolMessage, Any]) -> str | None:
    """Return proposal_id when the tool message is a persisted HITL gate row."""
    payload = get_hitl_payload(message)
    if not payload:
        return None
    proposal_id = payload.get("proposal_id")
    return proposal_id if isinstance(proposal_id, str) and proposal_id else None


def is_hitl_skipped_sibling_message(message: Union[ToolMessage, Any]) -> bool:
    """Return True for sibling tool rows skipped while another call awaits HITL."""
    return getattr(message, "content", None) == HITL_SKIPPED_TOOL_CONTENT


def is_placeholder_tool_message(message: Union[ToolMessage, Any]) -> bool:
    """Return True when a tool message is a HITL pause placeholder, not a real result."""
    if is_hitl_skipped_sibling_message(message):
        return True
    return is_hitl_approval_request(message)


def build_hitl_rejected_ai_message(tool_name: str) -> str:
    """Deterministic assistant reply for a rejected HITL continuation."""
    return f"The '{tool_name}' request was rejected. No action was taken."


