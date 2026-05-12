"""Service layer for HITL approvals."""

import hashlib
import json
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.core.exceptions import ResourceNotFoundError, ValidationError
from apps.shared.db.models import HitlApproval
from apps.shared.utils.logger import get_logger

from .domain import (
    HITL_RESOLUTION_REJECTED,
    HITL_STATUS_APPROVED,
    HITL_STATUS_EXECUTED,
    HITL_STATUS_EXPIRED,
    HITL_STATUS_PENDING,
    HITL_STATUS_REJECTED,
    HitlResolveResult,
)
from .repository import HitlApprovalRepository
from .utils import build_hitl_rejected_ai_message

HITL_CANCEL_REASON_SUPERSEDED: str = "superseded_by_new_user_message"


class HitlApprovalService:
    """Business logic for HITL approvals."""

    def __init__(self, tenant_id: int, db: AsyncSession):
        self.tenant_id = tenant_id
        self.db = db
        self.repository = HitlApprovalRepository(db)
        self.logger = get_logger(HitlApprovalService.__name__)

    @staticmethod
    def build_args_hash(tool_args: dict[str, Any]) -> str:
        encoded = json.dumps(tool_args or {}, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    @classmethod
    def build_proposal_id(
        cls,
        *,
        thread_id: str,
        session_id: str,
        tool_name: str,
        tool_args: dict[str, Any],
    ) -> str:
        args_hash = cls.build_args_hash(tool_args)
        raw = f"{thread_id}:{session_id}:{tool_name}:{args_hash}"
        suffix = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]
        return f"hitl_{suffix}"

    @staticmethod
    def _reset_approval_for_new_attempt(
        approval: HitlApproval,
        *,
        session_id: str,
        agent_id: int,
        tool_name: str,
        tool_args: dict[str, Any],
        risk_level: str,
        requested_by: int,
        expires_at: datetime | None,
        now: datetime,
    ) -> None:
        approval.status = HITL_STATUS_PENDING
        approval.session_id = session_id
        approval.agent_id = agent_id
        approval.tool_name = tool_name
        approval.tool_args = tool_args
        approval.args_hash = HitlApprovalService.build_args_hash(tool_args)
        approval.risk_level = risk_level
        approval.requested_by = requested_by
        approval.reason = None
        approval.approved_by = None
        approval.approved_at = None
        approval.rejected_by = None
        approval.rejected_at = None
        approval.execution_status = None
        approval.execution_error = None
        approval.executed_at = None
        approval.expires_at = expires_at
        approval.version += 1
        approval.updated_at = now

    async def _expire_if_needed(self, approval: HitlApproval) -> HitlApproval:
        if approval.status == HITL_STATUS_PENDING and approval.expires_at:
            now = datetime.now(UTC)
            if approval.expires_at < now:
                approval.status = HITL_STATUS_EXPIRED
                approval.updated_at = now
                return await self.repository.save(approval)
        return approval

    async def cancel_superseded_pending_for_thread(
        self,
        thread_id: str,
        *,
        reason: str = HITL_CANCEL_REASON_SUPERSEDED,
    ) -> int:
        """Cancel open pending approvals when the user starts an unrelated chat turn."""
        return await self.repository.cancel_all_pending_by_thread(
            self.tenant_id,
            thread_id,
            reason=reason,
        )

    async def get_approval(self, proposal_id: str) -> HitlApproval:
        approval = await self.repository.get_by_proposal_id(self.tenant_id, proposal_id)
        if not approval:
            raise ResourceNotFoundError(f"HITL proposal not found: {proposal_id}")

        return await self._expire_if_needed(approval)

    async def get_or_create_pending(
        self,
        *,
        tenant_id: int,
        thread_id: str,
        session_id: str,
        agent_id: int,
        proposal_id: str,
        tool_name: str,
        tool_args: dict[str, Any],
        risk_level: str,
        requested_by: int,
        expires_in_seconds: int = 900,
    ) -> HitlApproval:
        existing = await self.repository.get_by_proposal_id(tenant_id, proposal_id)
        now = datetime.now(UTC)
        expires_at = now + timedelta(seconds=expires_in_seconds) if expires_in_seconds > 0 else None

        if existing:
            existing = await self._expire_if_needed(existing)
            if existing.status == HITL_STATUS_EXPIRED:
                self._reset_approval_for_new_attempt(
                    existing,
                    session_id=session_id,
                    agent_id=agent_id,
                    tool_name=tool_name,
                    tool_args=tool_args,
                    risk_level=risk_level,
                    requested_by=requested_by,
                    expires_at=expires_at,
                    now=now,
                )
                await self.repository.save(existing)
            return existing

        approval = HitlApproval(
            tenant_id=tenant_id,
            thread_id=thread_id,
            session_id=session_id,
            agent_id=agent_id,
            proposal_id=proposal_id,
            version=1,
            tool_name=tool_name,
            tool_args=tool_args,
            args_hash=self.build_args_hash(tool_args),
            risk_level=risk_level,
            policy_snapshot={"mode": "always", "source": "tool_config"},
            status=HITL_STATUS_PENDING,
            requested_by=requested_by,
            expires_at=expires_at,
            created_at=now,
            updated_at=now,
        )
        return await self.repository.save(approval)

    async def approve(self, proposal_id: str, version: int, user_id: int, comment: str | None = None) -> HitlApproval:
        approval = await self.get_approval(proposal_id)

        if approval.status == HITL_STATUS_APPROVED:
            return approval

        if approval.status != HITL_STATUS_PENDING:
            raise ValidationError(
                f"proposal {proposal_id} is not pending",
                details={"status": approval.status},
            )

        approval = await self._expire_if_needed(approval)
        if approval.status == HITL_STATUS_EXPIRED:
            raise ValidationError("proposal expired", details={"status": HITL_STATUS_EXPIRED})

        if approval.version != version:
            raise ValidationError(
                "version conflict",
                details={"current_version": approval.version},
            )

        approval.status = HITL_STATUS_APPROVED
        approval.reason = comment
        approval.approved_by = user_id
        approval.approved_at = datetime.now(UTC)
        approval.version += 1
        approval.updated_at = datetime.now(UTC)
        return await self.repository.save(approval)

    async def reject(self, proposal_id: str, version: int, user_id: int, comment: str | None = None) -> HitlResolveResult:
        approval = await self.get_approval(proposal_id)

        if approval.status == HITL_STATUS_REJECTED:
            ack_message = await self._finalize_terminal_resolution(approval, HITL_RESOLUTION_REJECTED)
            return self._to_resolve_result(approval, ack_message=ack_message)

        if approval.status != HITL_STATUS_PENDING:
            raise ValidationError(
                f"proposal {proposal_id} is not pending",
                details={"status": approval.status},
            )

        approval = await self._expire_if_needed(approval)
        if approval.status == HITL_STATUS_EXPIRED:
            raise ValidationError("proposal expired", details={"status": HITL_STATUS_EXPIRED})

        if approval.version != version:
            raise ValidationError(
                "version conflict",
                details={"current_version": approval.version},
            )

        approval.status = HITL_STATUS_REJECTED
        approval.reason = comment
        approval.rejected_by = user_id
        approval.rejected_at = datetime.now(UTC)
        approval.version += 1
        approval.updated_at = datetime.now(UTC)
        approval = await self.repository.save(approval)
        ack_message = await self._finalize_terminal_resolution(approval, HITL_RESOLUTION_REJECTED)
        return self._to_resolve_result(approval, ack_message=ack_message)

    @staticmethod
    def _to_resolve_result(approval: HitlApproval, *, ack_message: str | None) -> HitlResolveResult:
        return HitlResolveResult(
            proposal_id=approval.proposal_id,
            status=approval.status,
            version=approval.version,
            needs_agent_resume=False,
            ack_message=ack_message,
        )

    def _build_persistence_config(self, approval: HitlApproval) -> RunnableConfig:
        from apps.tenant_app_service.agents.context import (
            create_agent_runtime_context,
            create_agent_runtime_tenant_context,
        )
        from apps.tenant_app_service.agents.domain import AgentUserContext

        tenant_ctx = create_agent_runtime_tenant_context(
            tenant_id=self.tenant_id,
            tenant_name="",
            config={},
        )
        user_ctx = AgentUserContext(
            user_id=approval.requested_by,
            username="",
            role="user",
            tenant_id=self.tenant_id,
            tenant_name="",
        )
        runtime_ctx = create_agent_runtime_context(
            tenant_context=tenant_ctx,
            user_context=user_ctx,
            agent_id=approval.agent_id,
            agent_name="",
            thread_id=approval.thread_id,
            session_id=approval.session_id or "",
        )
        return {
            "configurable": {
                "thread_id": approval.thread_id,
                "runtime": runtime_ctx.model_dump(),
            }
        }

    async def _finalize_terminal_resolution(self, approval: HitlApproval, resolution: str) -> str | None:
        """Persist a user-facing AI ack for terminal HITL; tool rows stay immutable."""
        if resolution != HITL_RESOLUTION_REJECTED:
            raise ValidationError(f"unsupported terminal resolution: {resolution}")

        from apps.tenant_app_service.agents.memory.conversation_memory_manager import (
            ConversationMemoryManager,
        )
        from apps.tenant_app_service.chat.message_repository import MessageRepository

        tool_name = approval.tool_name or "tool"
        ai_content = build_hitl_rejected_ai_message(tool_name)

        if not approval.session_id:
            self.logger.warning(
                "Terminal HITL resolution missing anchor session for proposal_id=%s",
                approval.proposal_id,
            )
            return ai_content

        message_repository = MessageRepository(self.db)
        for message in await message_repository.get_messages_by_session(approval.session_id):
            if message.type == "ai" and message.content == ai_content:
                return None

        ai_message = AIMessage(
            id=str(uuid4()),
            content=ai_content,
            additional_kwargs={"session_id": approval.session_id},
        )
        manager = ConversationMemoryManager(
            db_session=self.db,
            thread_id=approval.thread_id,
            tenant_id=self.tenant_id,
            agent_id=approval.agent_id,
        )
        await manager.add_messages([ai_message], self._build_persistence_config(approval), deduplicate=True)
        return ai_content

    async def mark_executed(self, proposal_id: str, success: bool, error: str | None = None) -> None:
        approval = await self.get_approval(proposal_id)
        if approval.status == HITL_STATUS_EXPIRED:
            return
        approval.status = HITL_STATUS_EXECUTED
        approval.execution_status = "success" if success else "failed"
        approval.execution_error = error
        approval.executed_at = datetime.now(UTC)
        approval.updated_at = datetime.now(UTC)
        await self.repository.save(approval)

    @asynccontextmanager
    async def execution_state_manager(self, proposal_id: str):
        """Track approval execution status around real tool invocation."""
        try:
            yield
        except Exception as e:
            await self.mark_executed(proposal_id, success=False, error=str(e))
            raise
        else:
            await self.mark_executed(proposal_id, success=True)
