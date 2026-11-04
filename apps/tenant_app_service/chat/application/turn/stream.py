"""Chat turn application mixins — composed by ``ChatTurnService``."""

from __future__ import annotations

import asyncio
import json
from typing import AsyncIterator

from apps.shared.schemas.user import UserDTO
from apps.tenant_app_service.agents.context import extract_runtime_context
from apps.tenant_app_service.agents.metrics import session_tracker
from apps.tenant_app_service.chat.application.runs.thread_run_service import ThreadRunService
from apps.tenant_app_service.chat.domain import AgentRun
from apps.tenant_app_service.chat.schemas import ChatRequest
from apps.tenant_app_service.chat.streaming import (
    PreparedChatStream,
    format_user_stream_error,
    is_transient_postgres_connection_error,
    user_stream_error_sse_payload,
)


class ChatTurnStreamMixin:
    _format_user_stream_error = staticmethod(format_user_stream_error)

    async def _finish_graph_stream(
        self,
        agent_graph,
        config: dict,
        run_id: str | None,
        *,
        failed: bool = False,
        cancelled: bool = False,
    ) -> None:
        from apps.tenant_app_service.agents.langgraph_invoke import (
            AgentInvokeOutcome,
            classify_invoke_outcome,
        )

        if not run_id:
            return
        thread_runs = self._thread_runs()
        if cancelled:
            await thread_runs.on_invoke_outcome(run_id, AgentInvokeOutcome.CANCELLED)
            return
        if failed:
            run = await thread_runs.get_run(run_id)
            if run and AgentRun.from_state(run).is_cancelled:
                await thread_runs.on_invoke_outcome(run_id, AgentInvokeOutcome.CANCELLED)
                return
            await thread_runs.on_invoke_outcome(run_id, AgentInvokeOutcome.FAILED)
            return
        run = await thread_runs.get_run(run_id)
        if run and AgentRun.from_state(run).is_cancelled:
            await thread_runs.on_invoke_outcome(run_id, AgentInvokeOutcome.CANCELLED)
            return
        outcome = await classify_invoke_outcome(agent_graph, config)
        await thread_runs.on_invoke_outcome(run_id, outcome)

    async def _run_is_cancelled_in_db(self, run_id: str | None) -> bool:
        if not run_id:
            return False
        return await self._thread_runs().is_run_cancelled(run_id)

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

    async def _iter_graph_sse_events(
        self,
        agent_graph,
        graph_input,
        *,
        config,
        runtime_context,
        max_pg_retries: int = 3,
    ) -> AsyncIterator[str]:
        """Yield SSE lines from LangGraph; retry only before first event (checkpoint read)."""
        for attempt in range(max_pg_retries):
            yielded = False
            try:
                async with session_tracker(runtime_context):
                    async for event in agent_graph.astream_events(
                        graph_input,
                        config=config,
                        version="v2",
                    ):
                        yielded = True
                        sse_payload = self._stream_event_to_sse(event)
                        if sse_payload:
                            yield sse_payload
                return
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                if (
                    not yielded
                    and attempt + 1 < max_pg_retries
                    and is_transient_postgres_connection_error(exc)
                ):
                    await asyncio.sleep(0.25 * (attempt + 1))
                    continue
                raise

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
        ephemeral_graph: bool = False,
    ) -> AsyncIterator[str]:
        """Execute one streaming turn and yield SSE payload lines."""
        if ephemeral_graph:
            async for line in self._run_stream_turn_ephemeral(
                request=request,
                current_user=current_user,
                session_id=session_id,
                agent_id=agent_id,
                agent_name=agent_name,
                access_token=access_token,
                initial_messages=initial_messages,
                run_id=run_id,
                trigger_message_id=trigger_message_id,
                invoke_index=invoke_index,
            ):
                yield line
            return

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
            if await self._run_is_cancelled_in_db(run_id):
                return
            await self._thread_runs().mark_run_running(run_id)

        stream_failed = False
        stream_cancelled = False
        try:
            async for sse_payload in self._iter_graph_sse_events(
                agent_graph,
                {
                    "messages": initial_messages,
                    "loop_count": 0,
                    "tool_call_counts": {},
                },
                config=config,
                runtime_context=runtime_context,
            ):
                yield sse_payload
        except asyncio.CancelledError:
            if run_id and await self._run_is_cancelled_in_db(run_id):
                stream_cancelled = True
            else:
                stream_failed = True
            raise
        except Exception:
            stream_failed = True
            raise
        finally:
            if run_id:
                if not stream_cancelled and await self._run_is_cancelled_in_db(run_id):
                    stream_cancelled = True
                await self._finish_graph_stream(
                    agent_graph,
                    config,
                    run_id,
                    failed=stream_failed,
                    cancelled=stream_cancelled,
                )

        self.logger.info(
            "Background stream completed for agent %s session %s",
            agent_id,
            session_id,
        )
        self.schedule_session_end(
            session_id=session_id,
            thread_id=request.thread_id or runtime_context.thread_id,
            run_id=run_id,
        )

    async def _run_stream_turn_ephemeral(
        self,
        *,
        request: ChatRequest,
        current_user: UserDTO,
        session_id: str,
        agent_id: int,
        agent_name: str,
        access_token: str | None,
        initial_messages: list,
        run_id: str | None,
        trigger_message_id: str | None,
        invoke_index: int,
    ) -> AsyncIterator[str]:
        """Stream turn without holding a DB connection during LangGraph / LLM I/O."""
        from apps.tenant_app_service.chat.turn_db import turn_service_session

        agent_graph = None
        config = None
        runtime_context = None
        async with turn_service_session(self.tenant_id) as prep:
            tenant = await prep.get_tenant_domain()
            agent_graph, capability_profile = await prep._get_agent_graph(agent_id, current_user)
            config = prep._build_runtime_config(
                tenant=tenant,
                current_user=current_user,
                request=request,
                agent_id=agent_id,
                agent_name=agent_name,
                session_id=session_id,
                access_token=access_token,
                capability_profile=capability_profile,
                run_id=run_id,
                trigger_message_id=trigger_message_id,
                invoke_index=invoke_index,
                pin_graph_db_session=False,
            )
            runtime_context = extract_runtime_context(config)
            if run_id:
                if await prep._run_is_cancelled_in_db(run_id):
                    return
                await ThreadRunService(prep.db, prep.tenant_id).mark_run_running(run_id)

        graph_input = {
            "messages": initial_messages,
            "loop_count": 0,
            "tool_call_counts": {},
        }
        stream_failed = False
        stream_cancelled = False
        try:
            async for sse_payload in prep._iter_graph_sse_events(
                agent_graph,
                graph_input,
                config=config,
                runtime_context=runtime_context,
            ):
                yield sse_payload
        except asyncio.CancelledError:
            async with turn_service_session(self.tenant_id) as check:
                if run_id and await check._run_is_cancelled_in_db(run_id):
                    stream_cancelled = True
                else:
                    stream_failed = True
            raise
        except Exception:
            stream_failed = True
            raise
        finally:
            if run_id:
                async with turn_service_session(self.tenant_id) as fin:
                    if not stream_cancelled and await fin._run_is_cancelled_in_db(run_id):
                        stream_cancelled = True
                    await fin._finish_graph_stream(
                        agent_graph,
                        config,
                        run_id,
                        failed=stream_failed,
                        cancelled=stream_cancelled,
                    )
            async with turn_service_session(self.tenant_id) as fin:
                self.logger.info(
                    "Background stream completed for agent %s session %s",
                    agent_id,
                    session_id,
                )
                fin.schedule_session_end(
                    session_id=session_id,
                    thread_id=request.thread_id or runtime_context.thread_id,
                    run_id=run_id,
                )

    async def run_hitl_checkpoint_resume_stream(
        self,
        *,
        request: ChatRequest,
        current_user: UserDTO,
        session_id: str,
        agent_id: int,
        agent_name: str,
        run_id: str,
        trigger_message_id: str | None,
        invoke_index: int,
        proposal_id: str,
        access_token: str | None = None,
    ) -> AsyncIterator[str]:
        """Resume a paused HITL run from LangGraph checkpoint (after approve)."""
        from langgraph.types import Command

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
            skip_load_history=True,
            hitl_proposal_id=proposal_id,
        )
        runtime_context = extract_runtime_context(config)

        if await self._run_is_cancelled_in_db(run_id):
            return

        stream_failed = False
        stream_cancelled = False
        try:
            async for sse_payload in self._iter_graph_sse_events(
                agent_graph,
                Command(
                    resume={
                        "interaction_type": "tool_approval",
                        "action": "approved",
                        "proposal_id": proposal_id,
                    }
                ),
                config=config,
                runtime_context=runtime_context,
            ):
                yield sse_payload
        except asyncio.CancelledError:
            if await self._run_is_cancelled_in_db(run_id):
                stream_cancelled = True
            else:
                stream_failed = True
            raise
        except Exception:
            stream_failed = True
            raise
        finally:
            if not stream_cancelled and await self._run_is_cancelled_in_db(run_id):
                stream_cancelled = True
            await self._finish_graph_stream(
                agent_graph,
                config,
                run_id,
                failed=stream_failed,
                cancelled=stream_cancelled,
            )

        self.schedule_session_end(
            session_id=session_id,
            thread_id=request.thread_id or runtime_context.thread_id,
            run_id=run_id,
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
        run_cancelled = False
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
        except asyncio.CancelledError:
            if prepared.run_id and await self._run_is_cancelled_in_db(prepared.run_id):
                run_cancelled = True
            else:
                raise
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
            if run_cancelled or (
                prepared.run_id and await self._run_is_cancelled_in_db(prepared.run_id)
            ):
                cancelled_data = {
                    "type": "cancelled",
                    "session_id": session_id,
                    "run_id": prepared.run_id,
                }
                await event_queue.put(f"data: {json.dumps(cancelled_data)}\n\n")
            done_data = {"type": "done", "session_id": session_id}
            await event_queue.put(f"data: {json.dumps(done_data)}\n\n")
            await event_queue.put(None)
