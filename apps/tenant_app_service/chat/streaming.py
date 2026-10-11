"""Streaming chat execution helpers for ChatService."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, AsyncIterator
from uuid import uuid4

from langchain_core.messages import HumanMessage, SystemMessage

from apps.shared.core.exceptions import DomainException
from apps.shared.db.session import app_db_session
from apps.shared.schemas.user import UserDTO
from apps.tenant_app_service.agents.context import extract_runtime_context
from apps.tenant_app_service.agents.metrics import session_tracker
from apps.tenant_app_service.chat.schemas import ChatRequest

if TYPE_CHECKING:
    from apps.tenant_app_service.chat.service import ChatService

# Keep bytes flowing during long LLM/tool gaps so proxies and browsers do not idle-close SSE.
SSE_HEARTBEAT_INTERVAL_SECONDS = 20
SSE_HEARTBEAT_PAYLOAD = ": ping\n\n"

STREAM_ERROR_KIND_DOMAIN = "domain"
STREAM_ERROR_KIND_RATE_LIMIT = "rate_limit"
STREAM_ERROR_KIND_AUTH = "auth"
STREAM_ERROR_KIND_TIMEOUT = "timeout"
STREAM_ERROR_KIND_CONNECTION = "connection"
STREAM_ERROR_KIND_INTERNAL = "internal"

STREAM_ERROR_GENERIC_MESSAGE = "Something went wrong while processing your request. Please try again."


def format_user_stream_error(error: BaseException) -> str:
    """Map an exception to a short, user-safe stream error message."""
    if isinstance(error, DomainException):
        return error.message

    error_message = str(error)
    lowered = error_message.lower()
    if "rate limit" in lowered:
        return "Rate limit exceeded. Please try again in a moment."
    if "api key" in lowered or "authentication" in lowered:
        return "Configuration error: Invalid API credentials."
    if "timeout" in lowered:
        return "Request timed out. Please try again."
    if "connection" in lowered:
        return "Connection error. Please check your network and try again."
    if error_message.strip():
        return f"An error occurred: {error_message}"
    return STREAM_ERROR_GENERIC_MESSAGE


def stream_error_kind(error: BaseException) -> str:
    """Stable category for clients that map errors to i18n (optional)."""
    if isinstance(error, DomainException):
        return STREAM_ERROR_KIND_DOMAIN

    lowered = str(error).lower()
    if "rate limit" in lowered:
        return STREAM_ERROR_KIND_RATE_LIMIT
    if "api key" in lowered or "authentication" in lowered:
        return STREAM_ERROR_KIND_AUTH
    if "timeout" in lowered:
        return STREAM_ERROR_KIND_TIMEOUT
    if "connection" in lowered:
        return STREAM_ERROR_KIND_CONNECTION
    return STREAM_ERROR_KIND_INTERNAL


def user_stream_error_sse_payload(error: BaseException) -> dict[str, str]:
    """Build SSE error event fields for a failed stream turn."""
    return {
        "type": "error",
        "message": format_user_stream_error(error),
        "error_code": type(error).__name__,
        "error_kind": stream_error_kind(error),
    }


@dataclass
class PreparedChatStream:
    """Setup result for a stream turn. Safe to use after the setup session closes."""

    session_id: str
    agent_id: int
    agent_name: str
    initial_messages: list[Any]
    thread_title: str | None


class ChatStreamingMixin:
    """Streaming turn orchestration mixed into ChatService."""

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

    def _build_initial_agent_messages(self, lc_messages: list, request: ChatRequest) -> list:
        """Build agent initial state messages.

        Normal sends persist the human message before invocation, so only ephemeral
        system context is passed in state. HITL continuations include the hidden human
        resume signal.
        """
        if self._is_hitl_continuation(request):
            return lc_messages
        return [message for message in lc_messages if isinstance(message, SystemMessage)]

    async def _persist_incoming_human_message(
        self,
        *,
        lc_messages: list,
        config: dict,
        thread_id: str,
    ) -> None:
        """Persist the incoming human message before the agent starts."""
        from apps.tenant_app_service.agents.memory.conversation_memory_manager import (
            ConversationMemoryManager,
        )

        human_messages = [message for message in lc_messages if isinstance(message, HumanMessage)]
        if not human_messages:
            return

        runtime = extract_runtime_context(config)
        manager = ConversationMemoryManager(
            db_session=self.db,
            thread_id=thread_id,
            tenant_id=self.tenant_id,
            agent_id=runtime.agent_id,
        )
        await manager.add_messages(human_messages, config, deduplicate=True)
        self.logger.info(
            "Persisted incoming human message for thread %s session %s",
            thread_id,
            runtime.session_id,
        )

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
        self: ChatService,
        *,
        request: ChatRequest,
        current_user: UserDTO,
        session_id: str,
        agent_id: int,
        agent_name: str,
        access_token: str | None,
        initial_messages: list,
    ) -> AsyncIterator[str]:
        """Execute one streaming turn and yield SSE payload lines."""
        tenant = await self._get_tenant_domain()
        config = self._build_runtime_config(
            tenant=tenant,
            current_user=current_user,
            request=request,
            agent_id=agent_id,
            agent_name=agent_name,
            session_id=session_id,
            access_token=access_token,
            db_session=self.db,
            capability_profile=None,
        )
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
        )
        runtime_context = extract_runtime_context(config)

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

        self.logger.info(
            "Background stream completed for agent %s session %s",
            agent_id,
            session_id,
        )
        self.schedule_session_end(
            session_id=session_id,
            thread_id=request.thread_id or runtime_context.thread_id,
        )

    async def _run_agent_and_emit(
        self: ChatService,
        *,
        event_queue: asyncio.Queue[str | None],
        tenant_id: int,
        request: ChatRequest,
        current_user: UserDTO,
        session_id: str,
        agent_id: int,
        agent_name: str,
        access_token: str | None,
        initial_messages: list,
    ) -> None:
        """Run the agent in the background and push SSE payloads into a queue."""
        from apps.tenant_app_service.chat.service import ChatService

        try:
            async with app_db_session() as db:
                stream_service = ChatService(tenant_id, db)
                async for payload in stream_service.run_stream_turn(
                    request=request,
                    current_user=current_user,
                    session_id=session_id,
                    agent_id=agent_id,
                    agent_name=agent_name,
                    access_token=access_token,
                    initial_messages=initial_messages,
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

    async def prepare_chat_stream(
        self: ChatService,
        request: ChatRequest,
        current_user: UserDTO,
        access_token: str | None = None,
    ) -> PreparedChatStream:
        """Persist setup for a stream turn. Caller should close the DB session after this."""
        agent_id = await self._resolve_agent_id(request)
        self.logger.info(
            f"Stream chat request received - tenant: {self.tenant_id}, agent: {agent_id}, "
            f"user: {current_user.username} (id: {current_user.id})"
        )

        await self._cancel_superseded_hitl_if_needed(request)

        session_id = str(uuid4())
        agent_graph, capability_profile = await self._get_agent_graph(agent_id, current_user)
        lc_messages = self._convert_to_langchain_messages([request.message])
        lc_messages = await self._inject_selected_context_resources(
            lc_messages,
            request.selected_resource_ids,
            thread_id=request.thread_id,
            selected_artifact_id=request.selected_artifact_id,
        )

        tenant = await self._get_tenant_domain()
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

        if not self._is_hitl_continuation(request):
            await self._persist_incoming_human_message(
                lc_messages=lc_messages,
                config=config,
                thread_id=request.thread_id or config["configurable"]["thread_id"],
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
        )

    async def iter_prepared_chat_stream(
        self: ChatService,
        request: ChatRequest,
        current_user: UserDTO,
        prepared: PreparedChatStream,
        access_token: str | None = None,
    ) -> AsyncIterator[str]:
        """Emit SSE for a prepared turn. Does not use the setup DB session."""
        event_queue: asyncio.Queue[str | None] = asyncio.Queue()
        yield f"data: {json.dumps({'type': 'session_started', 'session_id': prepared.session_id})}\n\n"
        if prepared.thread_title:
            yield f"data: {json.dumps({'type': 'update_thread_title', 'title': prepared.thread_title})}\n\n"

        asyncio.create_task(
            self._run_agent_and_emit(
                event_queue=event_queue,
                tenant_id=self.tenant_id,
                request=request,
                current_user=current_user,
                session_id=prepared.session_id,
                agent_id=prepared.agent_id,
                agent_name=prepared.agent_name,
                access_token=access_token,
                initial_messages=prepared.initial_messages,
            )
        )

        try:
            while True:
                try:
                    item = await asyncio.wait_for(
                        event_queue.get(),
                        timeout=SSE_HEARTBEAT_INTERVAL_SECONDS,
                    )
                except TimeoutError:
                    yield SSE_HEARTBEAT_PAYLOAD
                    continue
                if item is None:
                    break
                yield item
        except asyncio.CancelledError:
            self.logger.info(
                "SSE client disconnected for session %s; agent continues in background",
                prepared.session_id,
            )
            return

    async def chat_stream(
        self: ChatService,
        request: ChatRequest,
        current_user: UserDTO,
        access_token: str | None = None,
    ) -> AsyncIterator[str]:
        """Handle streaming chat request with durable background agent execution."""
        session_id = ""
        try:
            prepared = await self.prepare_chat_stream(request, current_user, access_token)
            session_id = prepared.session_id
            async for item in self.iter_prepared_chat_stream(request, current_user, prepared, access_token):
                yield item
        except asyncio.CancelledError:
            raise
        except Exception as e:
            error_message = str(e)
            self.logger.error(
                f"Error streaming from agent {request.agent_id} for tenant {self.tenant_id}: {error_message}",
                exc_info=True,
            )
            error_data = user_stream_error_sse_payload(e)
            yield f"data: {json.dumps(error_data)}\n\n"
            done_data = {"type": "done", "session_id": session_id}
            yield f"data: {json.dumps(done_data)}\n\n"
