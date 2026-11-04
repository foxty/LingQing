"""Composition root — wire domain ports to infrastructure (routers, tests)."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from apps.tenant_app_service.chat.application.runs.thread_run_service import ThreadRunService
from apps.tenant_app_service.chat.application.threads.thread_service import ThreadService
from apps.tenant_app_service.chat.application.turn import ChatTurnService
from apps.tenant_app_service.chat.domain.ports.agent_run import AgentRunRepositoryPort
from apps.tenant_app_service.chat.infrastructure.persistence.agent_run_repository import AgentRunRepository


def agent_run_repository(db: AsyncSession) -> AgentRunRepositoryPort:
    return AgentRunRepository(db)


def thread_run_service(db: AsyncSession, tenant_id: int) -> ThreadRunService:
    return ThreadRunService(db, tenant_id, run_repo=agent_run_repository(db))


def thread_service(tenant_id: int, db: AsyncSession) -> ThreadService:
    return ThreadService(tenant_id, db)


def chat_turn_service(tenant_id: int, db: AsyncSession) -> ChatTurnService:
    return ChatTurnService(tenant_id, db)
