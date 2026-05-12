"""Domain models for HITL approvals."""

from dataclasses import dataclass
from datetime import datetime
from typing import Final, Literal

HITL_RESOLUTION_REJECTED: Final = "rejected"

HITL_STATUS_PENDING: Final = "pending"
HITL_STATUS_APPROVED: Final = "approved"
HITL_STATUS_REJECTED: Final = "rejected"
HITL_STATUS_EXPIRED: Final = "expired"
HITL_STATUS_EXECUTED: Final = "executed"
HITL_STATUS_CANCELLED: Final = "cancelled"

HITL_ACTION_ALLOW: Final = "allow"
HITL_ACTION_REQUIRE_HITL: Final = "require_hitl"
HITL_ACTION_DENY: Final = "deny"

# Payload "type" describes message/event semantics for streaming + orchestration:
# - approval_request: frontend should present approval UI and backend should pause.
# - approval_result:  frontend should treat as resolved update and backend should resume/skip.
# Note: This is different from approval status (pending/approved/rejected/executed),
# which represents the latest state snapshot of an approval record.
HITL_PAYLOAD_TYPE_APPROVAL_REQUEST: Final = "approval_request"
HITL_PAYLOAD_TYPE_APPROVAL_RESULT: Final = "approval_result"

HitlStatus = Literal["pending", "approved", "rejected", "expired", "executed", "cancelled"]
HitlAction = Literal["allow", "require_hitl", "deny"]

HITL_BLOCKING_STATUSES: Final = frozenset({HITL_STATUS_PENDING, HITL_STATUS_APPROVED})


def is_hitl_blocking_status(status: str) -> bool:
    """Statuses that still require user action or an explicit resume turn."""
    return status in HITL_BLOCKING_STATUSES


@dataclass(frozen=True)
class HitlResolveResult:
    """Outcome of resolving a human interaction."""

    proposal_id: str
    status: str
    version: int
    needs_agent_resume: bool
    ack_message: str | None = None


@dataclass
class ApprovalDecision:
    """Policy decision for a tool call."""

    action: HitlAction
    reason: str
    risk_level: str = "medium"
    expires_at: datetime | None = None
