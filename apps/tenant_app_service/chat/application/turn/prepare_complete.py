"""Chat turn application mixins — composed by ``ChatTurnService``."""

from __future__ import annotations

from uuid import uuid4

from apps.shared.schemas.user import UserDTO
from apps.tenant_app_service.agents.context import create_thread_id, extract_runtime_context
from apps.tenant_app_service.agents.metrics import session_tracker
from apps.tenant_app_service.chat.application.runs.thread_run_service import ThreadRunService
from apps.tenant_app_service.chat.schemas import ChatRequest, ChatResponse, Message
from apps.tenant_app_service.chat.streaming import (
    PreparedChatStream,
)
from apps.tenant_app_service.chat.turn_admission import guard_thread_turn_start


class ChatTurnPrepareCompleteMixin:
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
        if request.thread_id:
            await self._reconcile_active_runs_before_new_turn(effective_thread_id, agent_id)
        if request.thread_id:
            await guard_thread_turn_start(
                self.db,
                tenant_id=self.tenant_id,
                thread_id=effective_thread_id,
                agent_id=agent_id,
                skip_busy_check=False,
            )

        if request.run_id:
            run_service = self._thread_runs()
            existing_run = await run_service.get_run(request.run_id)
            if not existing_run:
                from apps.shared.core.exceptions import ResourceNotFoundError

                raise ResourceNotFoundError(f"Agent run {request.run_id} not found")
            run_id = existing_run.id
            trigger_message_id = existing_run.trigger_message_id
            invoke_index = existing_run.invoke_index
            session_id = existing_run.session_id
            agent_id = existing_run.agent_id
            await run_service.mark_run_running(run_id)
        elif effective_thread_id:
            run_service = self._thread_runs()
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
                await self._thread_runs().mark_run_running(run_id)

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
        from apps.tenant_app_service.agents.message_content import normalize_message_content

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
                if await self._run_is_cancelled_in_db(prepared.run_id):
                    from apps.shared.core.exceptions import InternalServiceError

                    raise InternalServiceError("Agent run was cancelled")
                await self._thread_runs().mark_run_running(prepared.run_id)
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
                await self._thread_runs().mark_run_failed_unless_cancelled(prepared.run_id)
            raise InternalServiceError(f"Error invoking agent: {str(e)}") from e
        finally:
            if prepared.run_id:
                if not await self._run_is_cancelled_in_db(prepared.run_id):
                    await ThreadRunService(self.db, self.tenant_id).finalize_run_for_main(prepared.run_id)
            self.schedule_session_end(
                session_id=session_id,
                thread_id=request.thread_id or runtime_ctx.thread_id,
                run_id=prepared.run_id,
            )
