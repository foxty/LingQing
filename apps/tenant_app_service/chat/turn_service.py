"""Session-scoped chat turn executor (one ``AsyncSession`` per instance).

**Role:** Implement prepare / invoke / complete for a *single* DB transaction.
**Callers:** ``chat.application.turn_flow`` (production), or tests with a mock session.
**Must not:** Open ``app_db_session`` for multi-step HTTP/SSE flows — use application layer.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from typing import AsyncIterator
from uuid import uuid4

from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.core.exceptions import AuthorizationError
from apps.shared.schemas.user import UserDTO
from apps.tenant_app_service.agents.context import create_thread_id, extract_runtime_context
from apps.tenant_app_service.agents.metrics import session_tracker
from apps.tenant_app_service.chat.adapters import db_artifact_to_domain
from apps.tenant_app_service.chat.agent_run_domain import AgentRunStatus
from apps.tenant_app_service.chat.agent_run_repository import AgentRunRepository
from apps.tenant_app_service.chat.schemas import ChatRequest, ChatResponse, Message
from apps.tenant_app_service.chat.service_base import ChatServiceBase
from apps.tenant_app_service.chat.session_summary_manager import SessionSummaryManager
from apps.tenant_app_service.chat.streaming import (
    PreparedChatStream,
    format_user_stream_error,
    user_stream_error_sse_payload,
)
from apps.tenant_app_service.chat.thread_run_service import ThreadRunService
from apps.tenant_app_service.chat.thread_service import ThreadService
from apps.tenant_app_service.chat.thread_summary_manager import ThreadSummaryManager
from apps.tenant_app_service.chat.turn_admission import guard_thread_turn_start
from apps.tenant_app_service.tenant.domain import TenantDomain


class ChatTurnService(ChatServiceBase):
    """Prepare, invoke, and complete agent turns within one database session."""

    def _convert_to_langchain_messages(self, messages: list) -> list:
        """Convert SimpleMessage (from ChatRequest) to LangChain messages.

        Args:
            messages: List of SimpleMessage objects (role='human', content=str)

        Returns:
            List of HumanMessage objects with IDs and timestamps
        """
        return [
            HumanMessage(
                id=str(uuid4()),  # Generate unique ID for deduplication
                content=msg.content,
                additional_kwargs={"timestamp": datetime.now(UTC).isoformat()},
            )
            for msg in messages
        ]

    async def run_headless(
        self,
        *,
        user_id: int,
        agent_id: int,
        message: str,
        origin_thread_id: str | None = None,
        task_name: str | None = None,
    ) -> ChatResponse:
        """Run a chat turn on behalf of a user without an HTTP request."""
        from apps.tenant_app_service.chat.application import run_headless_chat_turn

        return await run_headless_chat_turn(
            self.tenant_id,
            self.db,
            user_id=user_id,
            agent_id=agent_id,
            message=message,
            origin_thread_id=origin_thread_id,
            task_name=task_name,
        )

    # ============================================================================
    # Chat Methods
    # ============================================================================

    async def chat(self, request: ChatRequest, current_user: UserDTO, access_token: str | None = None) -> ChatResponse:
        """Handle non-streaming chat (prepare + complete via short DB sessions)."""
        from apps.tenant_app_service.chat.application.turn_flow import run_non_stream_chat_turn

        return await run_non_stream_chat_turn(
            self.tenant_id,
            request,
            current_user,
            access_token=access_token,
        )

    async def create_thread_title_if_1st_message(self, content: str, thread_id: str, session_id: str) -> str:
        thread = await ThreadService(self.tenant_id, self.db).get_thread(thread_id)
        if thread is None:
            return None
        if thread.message_count == 0:
            from apps.tenant_app_service.agents.mini_agent import MiniAgentService

            self.logger.info(f"Generating thread title for first message in thread {thread_id}")
            thread_title = "New Thread"
            # update thread title base on first message if title is default
            mini_agent = MiniAgentService(tenant_id=self.tenant_id, db=self.db)
            try:
                thread_title = await mini_agent.common_llm_call(
                    agent_name="ThreadTitleGenerator",
                    user_prompt=content,
                    thread_id=thread_id,
                    session_id=session_id,
                )
            except Exception:
                self.logger.exception("Failed to generate thread title using MiniAgent.")
                thread_title = content[:15] + ("..." if len(content) > 20 else "")
            return thread_title
        else:
            return None

    async def _resolve_agent_id(self, request: ChatRequest) -> int:
        """Use the thread's immutable agent when a thread already exists."""
        if not request.thread_id:
            return request.agent_id
        thread = await ThreadService(self.tenant_id, self.db).get_thread(request.thread_id)
        if thread is None:
            return request.agent_id
        return thread.agent_id

    async def _get_system_agent_graph(self, agent_id: int):
        """Backward-compatible wrapper for system-agent graph loading."""
        graph, _profile = await self._get_agent_graph(agent_id, current_user=None)
        return graph

    async def _get_agent_graph(self, agent_id: int, current_user: UserDTO | None):
        """Load a system or custom agent graph plus its runtime capability profile."""
        from apps.shared.domain.actor import ActorContext
        from apps.shared.domain.types import ABAC_ACTION_READ
        from apps.tenant_app_service.agent_catalog.domain import SYSTEM_AGENT_ONE_ID
        from apps.tenant_app_service.agent_catalog.services import AgentCatalogService
        from apps.tenant_app_service.agents.system_agent_config import load_yaml_agent_config

        if agent_id <= SYSTEM_AGENT_ONE_ID or agent_id < 0:
            self.logger.info("Using system agent: %s", agent_id)
            graph = await self.agent_pool.get_or_create_agent(load_yaml_agent_config(agent_id))
            return graph, None

        if current_user is None:
            raise AuthorizationError("Custom agents require an authenticated user")

        from apps.shared.authz.ta_permissions import TenantAppPermissions
        from apps.shared.authz.ta_rbac import role_has_permission

        if not await role_has_permission(
            db=self.db,
            tenant_id=current_user.tenant_id,
            role_key=current_user.role,
            permission=TenantAppPermissions.AGENTS_READ,
        ):
            raise AuthorizationError("无权访问该智能体")

        from apps.tenant_app_service.agent_catalog.adapters import resolve_assignable_skills

        catalog = AgentCatalogService(tenant_id=self.tenant_id, db_session=self.db)
        actor = ActorContext(tenant_id=current_user.tenant_id, user_id=current_user.id, user_role=current_user.role)
        domain = await catalog.require_agent_access(agent_id=agent_id, actor=actor, action=ABAC_ACTION_READ)

        from apps.tenant_app_service.agents.custom_agent_loaded_config import (
            build_custom_agent_loaded_config,
            runtime_defaults_from_system_agent,
        )
        from apps.tenant_app_service.agents.system_agent_config import get_config_loader

        loader = get_config_loader()
        yaml_one = loader.get_system_agent_config(SYSTEM_AGENT_ONE_ID, materialize=False) or {}
        assignable_skills = resolve_assignable_skills(
            tenant_id=current_user.tenant_id, user_id=current_user.id
        )
        derived_tool_names = catalog.derived_tool_names(
            domain.profile,
            assignable_skills=assignable_skills,
        )
        preloaded = build_custom_agent_loaded_config(
            domain=domain,
            derived_tool_names=derived_tool_names,
            loader=loader,
            runtime_defaults=runtime_defaults_from_system_agent(yaml_one),
        )

        revision = domain.updated_at.isoformat() if domain.updated_at else "0"
        graph = await self.agent_pool.get_or_create_agent(
            preloaded,
            cache_revision=revision,
        )
        from apps.tenant_app_service.agents.runtime_capability import build_agent_capability_profile

        profile = await build_agent_capability_profile(
            self.db,
            tenant_id=self.tenant_id,
            actor=actor,
            agent_id=agent_id,
            assignable_skills=assignable_skills,
        )
        return graph, profile

    def _build_runtime_config(
        self,
        tenant: TenantDomain,
        current_user: UserDTO,
        request: ChatRequest,
        agent_id: int,
        agent_name: str,
        session_id: str,
        access_token: str | None = None,
        db_session: AsyncSession | None = None,
        capability_profile=None,
        run_id: str | None = None,
        trigger_message_id: str | None = None,
        invoke_index: int = 0,
    ) -> dict:
        """Build configuration for agent invocation.

        Args:
            tenant: Tenant domain object
            current_user: Current authenticated user
            request: Chat request
            agent_id: Agent ID
            agent_name: Agent name
            session_id: Unique session ID for this invocation

        Returns:
            Configuration dictionary with runtime context
        """
        from apps.tenant_app_service.agents.context import (
            create_agent_runtime_context,
            create_agent_runtime_tenant_context,
            create_agent_runtime_user_context,
        )

        thread_id = request.thread_id
        if not thread_id:
            thread_id = create_thread_id(current_user.id, self.tenant_id, agent_id)
        user_ctx = create_agent_runtime_user_context(current_user, access_token=access_token)
        tenant_config = tenant.config.to_dict() if tenant and tenant.config else {}
        tenant_ctx = create_agent_runtime_tenant_context(
            tenant_id=self.tenant_id,
            tenant_name=current_user.tenant_name,
            config=tenant_config,
        )

        runtime_ctx = create_agent_runtime_context(
            tenant_context=tenant_ctx,
            user_context=user_ctx,
            agent_id=agent_id,
            agent_name=agent_name,
            thread_id=thread_id,
            session_id=session_id,
            capability_profile=capability_profile,
        )

        # Build LangChain configuration
        hitl_resume = (
            {
                "proposal_id": request.hitl_proposal_id,
                "action": request.hitl_action,
            }
            if self._is_hitl_continuation(request)
            else None
        )

        config = {
            "configurable": {
                "thread_id": thread_id,
                "db_session": db_session or self.db,
                "runtime": runtime_ctx.model_dump(),
                "thinking_effort": request.thinking_effort,
                # On HITL resume: signals agent_base._load_history to rewrite the stale
                # PENDING ToolMessage, and tool_executor._handle_hitl_gate to use the
                # known proposal_id directly (avoids arg-hash drift from LLM re-generation).
                **(({"hitl_resume": hitl_resume}) if hitl_resume else {}),
                **({"run_id": run_id} if run_id else {}),
                **({"trigger_message_id": trigger_message_id} if trigger_message_id else {}),
                "invoke_index": invoke_index,
            },
            "recursion_limit": 999,  # Safety net, should be higher than MAX_ITERATIONS
        }
        self.logger.debug(
            f"Agent runtime context created - session_id: {session_id}, thread_id: {runtime_ctx.thread_id}, "
            f"user: {runtime_ctx.user.username}, role: {runtime_ctx.user.role}, "
            f"tenant: {runtime_ctx.user.tenant_name}, agent: {agent_name}"
        )

        return config

    async def _handle_session_end_async(
        self,
        session_id: str,
        thread_id: str,
    ) -> None:
        """Handle session end asynchronously.

        Creates session summary and checks if thread summary is needed.
        Works for both streaming and non-streaming modes.
        Statistics (tokens, duration, etc.) are tracked separately by Metrics V3.

        Args:
            session_id: Session ID
            thread_id: Thread ID

        Note:
            Creates its own database session to avoid conflicts with router-level
            session lifecycle. The router session is closed immediately after the
            response is sent, but this background task may still be running.
        """
        try:
            from apps.shared.db.session import app_db_session

            # Background tasks must use their own session: the router-level session
            # is closed as soon as the response is sent, which may happen before
            # this task finishes.  app_db_session() commits on clean exit and rolls
            # back on any exception.
            async with app_db_session() as db:
                # 1. Create session summary + mark messages as summarized, then commit.
                # These two writes must be persisted regardless of whether a thread
                # summary is triggered next.
                session_summary_manager = SessionSummaryManager(db, self.tenant_id)
                session_summary = await session_summary_manager.create_session_summary(
                    session_id=session_id,
                    thread_id=thread_id,
                )
                await db.commit()

                if not session_summary:
                    self.logger.warning(f"Failed to create session summary for session {session_id}")

                # 2. Check and create thread summary if needed.
                # ThreadSummaryManager.create_thread_summary() manages its own
                # commit/rollback internally.
                thread_summary_manager = ThreadSummaryManager(db, self.tenant_id)
                thread_summary = await thread_summary_manager.check_and_create_if_needed(thread_id)

                if thread_summary:
                    self.logger.info(f"Created thread summary v{thread_summary.version} for thread {thread_id}")

        except Exception as e:
            self.logger.error(
                f"Failed to handle session end for session {session_id}: {e}",
                exc_info=True,
            )

    async def _inject_message_attachments(
        self,
        lc_messages: list,
        *,
        selected_artifact_ids: list[int] | None = None,
        selected_artifact_id: int | None = None,
        current_user: UserDTO | None = None,
    ) -> list:
        """Inject @mention artifact context for the agent."""
        ids: list[int] = []
        if selected_artifact_ids:
            ids.extend(selected_artifact_ids)
        elif selected_artifact_id is not None:
            ids.append(selected_artifact_id)
        if not ids:
            return lc_messages
        return await self._inject_selected_artifacts(
            lc_messages,
            ids,
            current_user=current_user,
        )

    async def _inject_selected_artifacts(
        self,
        lc_messages: list,
        artifact_ids: list[int],
        *,
        current_user: UserDTO | None,
    ) -> list:
        """Inject artifact continuity context from artifact record ids (not thread-scoped)."""
        if not artifact_ids or current_user is None:
            return lc_messages

        from apps.shared.artifact.access import require_artifact_record_read

        context_lines = [
            "[Context] The user attached the following artifacts to continue working on:",
        ]
        metadata: list[dict] = []

        for artifact_id in artifact_ids:
            try:
                record = await require_artifact_record_read(
                    db=self.db,
                    tenant_id=self.tenant_id,
                    user_id=current_user.id,
                    user_role=current_user.role,
                    artifact_id=artifact_id,
                )
                artifact = db_artifact_to_domain(record)
                context_lines.append(
                    f"- Type: {artifact.artifact_type}, Title: {artifact.title}, "
                    f"Artifact id: {artifact.id}, Resource id: {artifact.resource_id}, "
                    f"URL: {artifact.url or 'n/a'}"
                )
                metadata.append(
                    {
                        "artifact_id": artifact.id,
                        "artifact_type": artifact.artifact_type,
                        "title": artifact.title or "Untitled",
                        "resource_id": artifact.resource_id,
                    }
                )
            except Exception as exc:
                self.logger.warning(
                    "Skipping inaccessible artifact %s for user %s: %s",
                    artifact_id,
                    current_user.id,
                    exc,
                )
                context_lines.append(f"- artifact id={artifact_id}: not accessible")
                metadata.append(
                    {
                        "artifact_id": artifact_id,
                        "artifact_type": "unknown",
                        "title": f"Artifact #{artifact_id}",
                        "inaccessible": True,
                    }
                )

        context_lines.append(
            "Use the tools appropriate to each artifact type to inspect or update the underlying resource."
        )
        lc_messages.insert(0, SystemMessage(content="\n".join(context_lines)))
        self._stamp_attached_artifacts(lc_messages, metadata)
        return lc_messages

    @staticmethod
    def _stamp_attached_artifacts(lc_messages: list, items: list[dict]) -> None:
        if not items:
            return
        chip_payload = [
            {
                "artifact_id": item["artifact_id"],
                "artifact_type": item.get("artifact_type", "unknown"),
                "title": item.get("title", "Untitled"),
                "resource_type": item.get("artifact_type", "unknown"),
                "resource_id": item["artifact_id"],
            }
            for item in items
        ]
        for msg in reversed(lc_messages):
            if isinstance(msg, HumanMessage):
                kwargs = dict(msg.additional_kwargs or {})
                kwargs["attached_artifacts"] = chip_payload
                msg.additional_kwargs = kwargs
                return

    def _is_hitl_continuation(self, request: ChatRequest) -> bool:
        """Whether this request is a HITL continuation request."""
        return bool(request.hitl_proposal_id and request.hitl_action)

    def schedule_session_end(self, session_id: str, thread_id: str | None) -> None:
        """Schedule async session summary work after a turn completes."""
        asyncio.create_task(
            self._handle_session_end_async(
                session_id=session_id,
                thread_id=thread_id,
            )
        )

    async def _cancel_superseded_hitl_if_needed(self, request: ChatRequest) -> None:
        """Cancel stale pending HITL when the user starts an unrelated chat turn."""
        if self._is_hitl_continuation(request) or not request.thread_id:
            return

        from apps.tenant_app_service.hitl.service import HitlApprovalService

        service = HitlApprovalService(self.tenant_id, self.db)
        cancelled = await service.cancel_superseded_pending_for_thread(request.thread_id)
        if cancelled:
            self.logger.info(
                "Cancelled %s superseded pending HITL approval(s) for thread %s",
                cancelled,
                request.thread_id,
            )

    async def _reconcile_active_runs_before_new_turn(self, thread_id: str, agent_id: int) -> None:
        """Close orphan agent runs so a new user message is not blocked after terminal HITL."""
        from datetime import UTC, datetime

        from apps.tenant_app_service.chat.session_domain import is_stale_running_session
        from apps.tenant_app_service.hitl.repository import HitlApprovalRepository

        run_repo = AgentRunRepository(self.db)
        hitl_repo = HitlApprovalRepository(self.db)
        pending = await hitl_repo.get_latest_pending_by_thread(self.tenant_id, thread_id)
        pending_session_id = pending.session_id if pending else None
        now = datetime.now(UTC)

        for run in await run_repo.list_active_for_thread_agent(thread_id, agent_id):
            if pending_session_id and run.session_id == pending_session_id:
                continue
            if run.status == AgentRunStatus.AWAITING_HITL or is_stale_running_session(run.created_at, now=now):
                await run_repo.set_status(
                    run.id,
                    status=AgentRunStatus.COMPLETED,
                    completed_at=now,
                )

    def _build_initial_agent_messages(self, lc_messages: list, request: ChatRequest) -> list:
        """Build agent initial state messages.

        Normal sends persist the human message before invocation, so only ephemeral
        system context is passed in state. HITL continuations include the hidden human
        resume signal.
        """
        if self._is_hitl_continuation(request):
            return lc_messages
        return [message for message in lc_messages if isinstance(message, SystemMessage)]

    @staticmethod
    def _stream_event_to_sse(event: dict) -> str | None:
        """Convert an astream_events payload to an SSE data line."""
        tags = event.get("tags", [])
        if "mini-agent" in tags:
            return None

        if event["event"] == "on_chat_model_stream":
            chunk = event["data"].get("chunk")
            if chunk and hasattr(chunk, "content") and chunk.content:
                data = {"type": "token", "content": chunk.content}
                return f"data: {json.dumps(data)}\n\n"
        if event["event"] == "on_tool_start":
            tool_name = event.get("name", "unknown")
            data = {
                "type": "tool_start",
                "tool_name": tool_name,
                "message": f"Using tool: {tool_name}",
            }
            return f"data: {json.dumps(data)}\n\n"
        if event["event"] == "on_tool_end":
            tool_name = event.get("name", "unknown")
            data = {
                "type": "tool_end",
                "tool_name": tool_name,
                "message": f"✅ Tool completed: {tool_name}",
            }
            return f"data: {json.dumps(data)}\n\n"
        return None

    _format_user_stream_error = staticmethod(format_user_stream_error)

    async def run_stream_turn(
        self,
        *,
        request: ChatRequest,
        current_user: UserDTO,
        session_id: str,
        agent_id: int,
        agent_name: str,
        access_token: str | None,
        initial_messages: list,
        run_id: str | None = None,
        trigger_message_id: str | None = None,
        invoke_index: int = 0,
    ) -> AsyncIterator[str]:
        """Execute one streaming turn and yield SSE payload lines."""
        tenant = await self.get_tenant_domain()
        agent_graph, capability_profile = await self._get_agent_graph(agent_id, current_user)
        config = self._build_runtime_config(
            tenant=tenant,
            current_user=current_user,
            request=request,
            agent_id=agent_id,
            agent_name=agent_name,
            session_id=session_id,
            access_token=access_token,
            db_session=self.db,
            capability_profile=capability_profile,
            run_id=run_id,
            trigger_message_id=trigger_message_id,
            invoke_index=invoke_index,
        )
        runtime_context = extract_runtime_context(config)

        if run_id:
            await AgentRunRepository(self.db).set_status(run_id, status=AgentRunStatus.RUNNING)

        try:
            async with session_tracker(runtime_context):
                async for event in agent_graph.astream_events(
                    {
                        "messages": initial_messages,
                        "loop_count": 0,
                        "tool_call_counts": {},
                    },
                    config=config,
                    version="v2",
                ):
                    sse_payload = self._stream_event_to_sse(event)
                    if sse_payload:
                        yield sse_payload
        except Exception:
            if run_id:
                await AgentRunRepository(self.db).set_status(run_id, status=AgentRunStatus.FAILED)
            raise

        self.logger.info(
            "Background stream completed for agent %s session %s",
            agent_id,
            session_id,
        )
        self.schedule_session_end(
            session_id=session_id,
            thread_id=request.thread_id or runtime_context.thread_id,
        )

    async def run_agent_and_emit_prepared(
        self,
        *,
        event_queue: asyncio.Queue[str | None],
        request: ChatRequest,
        current_user: UserDTO,
        prepared: PreparedChatStream,
        access_token: str | None = None,
    ) -> None:
        """Run a prepared stream turn and push SSE payloads into a queue."""
        session_id = prepared.session_id
        try:
            async for payload in self.run_stream_turn(
                request=request,
                current_user=current_user,
                session_id=session_id,
                agent_id=prepared.agent_id,
                agent_name=prepared.agent_name,
                access_token=access_token,
                initial_messages=prepared.initial_messages,
                run_id=prepared.run_id,
                trigger_message_id=prepared.trigger_message_id,
                invoke_index=prepared.invoke_index,
            ):
                await event_queue.put(payload)
        except Exception as exc:
            self.logger.error(
                "Background agent run failed for session %s: %s",
                session_id,
                exc,
                exc_info=True,
            )
            error_data = user_stream_error_sse_payload(exc)
            await event_queue.put(f"data: {json.dumps(error_data)}\n\n")
        finally:
            done_data = {"type": "done", "session_id": session_id}
            await event_queue.put(f"data: {json.dumps(done_data)}\n\n")
            await event_queue.put(None)

    async def prepare_chat_turn(
        self,
        request: ChatRequest,
        current_user: UserDTO,
        access_token: str | None = None,
        *,
        log_label: str = "Chat",
    ) -> PreparedChatStream:
        """Lock, reject concurrent turns, and persist the incoming human message.

        Runs in a short DB transaction; caller should commit by closing the session
        before invoking the agent.
        """
        agent_id = await self._resolve_agent_id(request)
        self.logger.info(
            "%s turn prepare tenant=%s agent=%s user_id=%s thread_id=%s",
            log_label,
            self.tenant_id,
            agent_id,
            current_user.id,
            request.thread_id,
        )

        await self._cancel_superseded_hitl_if_needed(request)

        run_id: str | None = None
        trigger_message_id: str | None = None
        invoke_index = 0
        session_id = str(uuid4())

        if self._is_hitl_continuation(request) and request.hitl_proposal_id:
            from apps.tenant_app_service.hitl.repository import HitlApprovalRepository

            approval = await HitlApprovalRepository(self.db).get_by_proposal_id(
                self.tenant_id, request.hitl_proposal_id
            )
            if approval and approval.session_id:
                session_id = approval.session_id
                existing_run = await AgentRunRepository(self.db).get_by_session_id(session_id)
                if existing_run:
                    run_id = existing_run.id
                    trigger_message_id = existing_run.trigger_message_id
                    invoke_index = existing_run.invoke_index
                    agent_id = existing_run.agent_id
                    await AgentRunRepository(self.db).set_status(run_id, status=AgentRunStatus.RUNNING)

        agent_graph, capability_profile = await self._get_agent_graph(agent_id, current_user)
        lc_messages = self._convert_to_langchain_messages([request.message])
        lc_messages = await self._inject_message_attachments(
            lc_messages,
            selected_artifact_ids=request.selected_artifact_ids,
            selected_artifact_id=request.selected_artifact_id,
            current_user=current_user,
        )

        tenant = await self.get_tenant_domain()
        config = self._build_runtime_config(
            tenant=tenant,
            current_user=current_user,
            request=request,
            agent_id=agent_id,
            agent_name=agent_graph.get_name(),
            session_id=session_id,
            access_token=access_token,
            capability_profile=capability_profile,
        )

        effective_thread_id = request.thread_id or config["configurable"]["thread_id"]
        if request.thread_id and not self._is_hitl_continuation(request):
            await self._reconcile_active_runs_before_new_turn(effective_thread_id, agent_id)
        if request.thread_id:
            await guard_thread_turn_start(
                self.db,
                tenant_id=self.tenant_id,
                thread_id=effective_thread_id,
                agent_id=agent_id,
                skip_busy_check=self._is_hitl_continuation(request),
            )

        if request.run_id and not self._is_hitl_continuation(request):
            run_repo = AgentRunRepository(self.db)
            existing_run = await run_repo.get_run(self.tenant_id, request.run_id)
            if not existing_run:
                from apps.shared.core.exceptions import ResourceNotFoundError

                raise ResourceNotFoundError(f"Agent run {request.run_id} not found")
            run_id = existing_run.id
            trigger_message_id = existing_run.trigger_message_id
            invoke_index = existing_run.invoke_index
            session_id = existing_run.session_id
            agent_id = existing_run.agent_id
            await run_repo.set_status(run_id, status=AgentRunStatus.RUNNING)
        elif effective_thread_id and not self._is_hitl_continuation(request):
            run_service = ThreadRunService(self.db, self.tenant_id)
            agent_ids = request.agent_ids if request.agent_ids is not None else [agent_id]
            _, runs = await run_service.send_human_and_create_runs(
                thread_id=effective_thread_id,
                content=request.message.content,
                agent_ids=agent_ids,
            )
            matching = next((r for r in runs if r.agent_id == agent_id), runs[0] if runs else None)
            if matching:
                run_id = matching.id
                trigger_message_id = matching.trigger_message_id
                invoke_index = matching.invoke_index
                session_id = matching.session_id
                await AgentRunRepository(self.db).set_status(run_id, status=AgentRunStatus.RUNNING)

        if run_id:
            config = self._build_runtime_config(
                tenant=tenant,
                current_user=current_user,
                request=request,
                agent_id=agent_id,
                agent_name=agent_graph.get_name(),
                session_id=session_id,
                access_token=access_token,
                capability_profile=capability_profile,
                run_id=run_id,
                trigger_message_id=trigger_message_id,
                invoke_index=invoke_index,
            )

        thread_title = await self.create_thread_title_if_1st_message(
            request.message.content, request.thread_id, session_id
        )
        if thread_title:
            self.logger.info(f"Created thread title to '{thread_title}' for thread {request.thread_id}")

        return PreparedChatStream(
            session_id=session_id,
            agent_id=agent_id,
            agent_name=agent_graph.get_name(),
            initial_messages=self._build_initial_agent_messages(lc_messages, request),
            thread_title=thread_title,
            run_id=run_id,
            trigger_message_id=trigger_message_id,
            invoke_index=invoke_index,
        )

    async def prepare_chat_stream(
        self,
        request: ChatRequest,
        current_user: UserDTO,
        access_token: str | None = None,
    ) -> PreparedChatStream:
        """Persist setup for a stream turn. Caller should close the DB session after this."""
        return await self.prepare_chat_turn(
            request,
            current_user,
            access_token=access_token,
            log_label="Stream chat",
        )

    async def complete_chat_turn(
        self,
        request: ChatRequest,
        current_user: UserDTO,
        prepared: PreparedChatStream,
        access_token: str | None = None,
    ) -> ChatResponse:
        """Run the agent for a turn prepared by ``prepare_chat_turn``."""
        from apps.tenant_app_service.agents.context import create_thread_id, extract_runtime_context
        from apps.tenant_app_service.agents.message_content import normalize_message_content
        from apps.tenant_app_service.agents.metrics import session_tracker

        agent_id = prepared.agent_id
        session_id = prepared.session_id
        tenant = await self.get_tenant_domain()
        agent_graph, capability_profile = await self._get_agent_graph(agent_id, current_user)

        config = self._build_runtime_config(
            tenant=tenant,
            current_user=current_user,
            request=request,
            agent_id=agent_id,
            agent_name=prepared.agent_name,
            session_id=session_id,
            access_token=access_token,
            capability_profile=capability_profile,
            run_id=prepared.run_id,
            trigger_message_id=prepared.trigger_message_id,
            invoke_index=prepared.invoke_index,
        )
        runtime_ctx = extract_runtime_context(config)

        try:
            if prepared.run_id:
                await AgentRunRepository(self.db).set_status(prepared.run_id, status=AgentRunStatus.RUNNING)
            async with session_tracker(runtime_ctx):
                result = await agent_graph.ainvoke(
                    {
                        "messages": prepared.initial_messages,
                        "loop_count": 0,
                        "tool_call_counts": {},
                    },
                    config=config,
                )

                last_message = result["messages"][-1]
                content = normalize_message_content(last_message.content)

                if not last_message.additional_kwargs.get("session_id"):
                    last_message.additional_kwargs["session_id"] = session_id

                self.logger.info(
                    "Chat turn completed tenant=%s agent=%s user=%s session=%s",
                    self.tenant_id,
                    agent_id,
                    current_user.username,
                    session_id,
                )

                effective_thread_id = request.thread_id or create_thread_id(
                    current_user.id, self.tenant_id, agent_id
                )

                return ChatResponse(
                    response=Message(
                        message_id=getattr(last_message, "id", None),
                        role="ai",
                        content=content,
                        agent_id=agent_id,
                        thread_id=effective_thread_id,
                        session_id=session_id,
                    ),
                    agent_id=agent_id,
                    tenant_id=self.tenant_id,
                )
        except Exception as e:
            self.logger.error(
                "Error invoking agent %s for tenant %s: %s",
                agent_id,
                self.tenant_id,
                str(e),
                exc_info=True,
            )
            from apps.shared.core.exceptions import InternalServiceError

            if prepared.run_id:
                await AgentRunRepository(self.db).set_status(prepared.run_id, status=AgentRunStatus.FAILED)
            raise InternalServiceError(f"Error invoking agent: {str(e)}") from e
        finally:
            self.schedule_session_end(session_id=session_id, thread_id=request.thread_id)

