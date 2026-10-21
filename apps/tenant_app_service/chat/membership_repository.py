"""Repository for shared thread user/agent memberships."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.db.models import ChatThreadAgentMember, ChatThreadUserMember
from apps.tenant_app_service.chat.thread_kinds import MEMBER_ROLE_OWNER


class ThreadMembershipRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def add_user_member(
        self,
        *,
        tenant_id: int,
        thread_id: str,
        user_id: int,
        role: str = MEMBER_ROLE_OWNER,
    ) -> ChatThreadUserMember:
        existing = await self.get_user_member(thread_id, user_id)
        if existing is not None:
            return existing
        row = ChatThreadUserMember(
            tenant_id=tenant_id,
            thread_id=thread_id,
            user_id=user_id,
            role=role,
        )
        self.db.add(row)
        await self.db.flush()
        await self.db.refresh(row)
        return row

    async def get_user_member(self, thread_id: str, user_id: int) -> ChatThreadUserMember | None:
        result = await self.db.execute(
            select(ChatThreadUserMember).where(
                ChatThreadUserMember.thread_id == thread_id,
                ChatThreadUserMember.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_user_members(self, thread_id: str) -> list[ChatThreadUserMember]:
        result = await self.db.execute(
            select(ChatThreadUserMember).where(ChatThreadUserMember.thread_id == thread_id)
        )
        return list(result.scalars().all())

    async def remove_user_member(self, thread_id: str, user_id: int) -> bool:
        row = await self.get_user_member(thread_id, user_id)
        if row is None:
            return False
        await self.db.delete(row)
        await self.db.flush()
        return True

    async def update_user_member_role(self, thread_id: str, user_id: int, role: str) -> bool:
        row = await self.get_user_member(thread_id, user_id)
        if row is None:
            return False
        row.role = role
        await self.db.flush()
        return True

    async def remove_agent_member(self, thread_id: str, agent_id: int) -> bool:
        row = await self.get_agent_member(thread_id, agent_id)
        if row is None:
            return False
        await self.db.delete(row)
        await self.db.flush()
        return True

    async def list_thread_ids_for_user(self, tenant_id: int, user_id: int) -> list[str]:
        result = await self.db.execute(
            select(ChatThreadUserMember.thread_id).where(
                ChatThreadUserMember.tenant_id == tenant_id,
                ChatThreadUserMember.user_id == user_id,
            )
        )
        return list(result.scalars().all())

    async def add_agent_member(
        self,
        *,
        tenant_id: int,
        thread_id: str,
        agent_id: int,
        display_alias: str | None = None,
    ) -> ChatThreadAgentMember:
        existing = await self.get_agent_member(thread_id, agent_id)
        if existing is not None:
            return existing
        row = ChatThreadAgentMember(
            tenant_id=tenant_id,
            thread_id=thread_id,
            agent_id=agent_id,
            display_alias=display_alias,
        )
        self.db.add(row)
        await self.db.flush()
        await self.db.refresh(row)
        return row

    async def get_agent_member(self, thread_id: str, agent_id: int) -> ChatThreadAgentMember | None:
        result = await self.db.execute(
            select(ChatThreadAgentMember).where(
                ChatThreadAgentMember.thread_id == thread_id,
                ChatThreadAgentMember.agent_id == agent_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_agent_members(self, thread_id: str) -> list[ChatThreadAgentMember]:
        result = await self.db.execute(
            select(ChatThreadAgentMember).where(ChatThreadAgentMember.thread_id == thread_id)
        )
        return list(result.scalars().all())

    async def count_agent_members(self, thread_id: str) -> int:
        members = await self.list_agent_members(thread_id)
        return len(members)
