"""Pure HITL payload inspection for the agent harness (no hitl module imports)."""

from __future__ import annotations

from typing import Any

from langchain_core.messages import ToolMessage

HITL_PAYLOAD_TYPE_APPROVAL_REQUEST = "approval_request"
HITL_PAYLOAD_TYPE_APPROVAL_RESULT = "approval_result"


def get_hitl_payload(message: ToolMessage | Any) -> dict[str, Any] | None:
    additional_kwargs = getattr(message, "additional_kwargs", None)
    if not isinstance(additional_kwargs, dict):
        return None
    payload = additional_kwargs.get("hitl")
    return payload if isinstance(payload, dict) else None


def is_hitl_approval_request(message: ToolMessage | Any, proposal_id: str | None = None) -> bool:
    payload = get_hitl_payload(message)
    if not payload or payload.get("type") != HITL_PAYLOAD_TYPE_APPROVAL_REQUEST:
        return False
    if proposal_id is not None:
        return payload.get("proposal_id") == proposal_id
    return True
