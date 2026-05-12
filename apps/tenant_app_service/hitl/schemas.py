"""API schemas for HITL approvals."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class HitlApprovalActionRequest(BaseModel):
    """Approve/reject request payload."""

    version: int = Field(..., ge=1)
    comment: str | None = None


class HitlApprovalResponse(BaseModel):
    """HITL approval response payload."""

    proposal_id: str
    status: str
    version: int
    thread_id: str
    tool_name: str
    tool_args: dict[str, Any]
    risk_level: str
    reason: str | None = None
    expires_at: datetime | None = None
    approved_by: int | None = None
    approved_at: datetime | None = None
    rejected_by: int | None = None
    rejected_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class HitlApprovalActionResponse(BaseModel):
    """Approve/reject action response."""

    proposal_id: str
    status: str
    version: int
    needs_agent_resume: bool = False
    ack_message: str | None = None
