"""AgentBase - Base class for all agents.

This module provides a reusable foundation for building agents with common
functionality like message trimming, stats tracking, and tool execution.

Architecture:
- AgentBase handles all generic logic (trimming, stats, limits, cleanup)
- Subclasses only need to define tools and system prompt
- Configuration-driven behavior for easy customization
"""

import time
from abc import ABC
from dataclasses import asdict
from datetime import UTC, datetime
from typing import List, Literal
from uuid import uuid4

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from sqlalchemy.ext.asyncio import AsyncSession
from typing_extensions import NotRequired, TypedDict

from apps.shared.utils.logger import get_logger
from apps.tenant_app_service.agents.agent_config import AgentConfig
from apps.tenant_app_service.agents.context import extract_runtime_context
from apps.tenant_app_service.agents.domain import (
    AgentLoadedConfig,
    AgentRuntimeContext,
    SkillState,
    ToolCache,
    ToolCallCounts,
)
from apps.tenant_app_service.agents.memory.conversation_memory_manager import ConversationMemoryManager
from apps.tenant_app_service.agents.message_content import ensure_visible_ai_content
from apps.tenant_app_service.agents.message_preparer import MessagePreparer
from apps.tenant_app_service.agents.metrics import llm_call_tracker
from apps.tenant_app_service.agents.model_binding_manager import ModelBindingManager
from apps.tenant_app_service.agents.tool_executor import ToolExecutor
from apps.tenant_app_service.hitl.utils import is_hitl_approval_request


class AgentState(TypedDict):
    """Base state schema for all agents."""

    messages: List[BaseMessage]  # Full message list (manually managed, no reducer)
    loop_count: int
    tool_call_counts: ToolCallCounts
    tool_cache: NotRequired[ToolCache]
    skill_state: NotRequired[SkillState]  # Skill runtime state
    hitl_blocked: NotRequired[bool]  # True when waiting for HITL approval/rejection


class AgentBase(ABC):
    def __init__(
        self,
        config: AgentLoadedConfig,
        *,
        config_overrides: dict | None = None,
    ):
        """Create an agent from a resolved document. Does not load YAML or catalog.

        Args:
            config: YAML-shaped agent document (``agent_id`` is a field)
            config_overrides: Optional overlay, e.g. ``{'max_loop_iterations': 10}``
        """
        self.agent_config = AgentConfig(config, config_overrides=config_overrides)
        self.logger = get_logger(__name__, self.agent_config.agent_name)
        self._model_binding_manager = ModelBindingManager(self.agent_config, self.logger)

        # Components for message and tool handling
        self.message_preparer = MessagePreparer(self.agent_config.agent_name)
        self.tool_executor = ToolExecutor(
            self.agent_config,
            self.agent_config.agent_name,
        )

        self.logger.info(f"Agent initialized: {self.agent_config}")

    @property
    def agent_id(self) -> int:
        """Get agent ID."""
        return self.agent_config.agent_id

    @property
    def agent_name(self) -> str:
        """Get agent name."""
        return self.agent_config.agent_name

    def _default_skill_state(self) -> SkillState:
        """Return default skill state for a run."""
        return {
            "loaded_skills": [],
            "skill_switch_loop": -1,
            "skill_history": [],
        }

    def _get_skill_state(self, state: AgentState, runtime: AgentRuntimeContext) -> SkillState:
        """Get normalized skill state from AgentState.

        This is the single source of truth for per-run skill state.
        """
        raw_state: SkillState = state.get("skill_state") or self._default_skill_state()
        loaded_skills_raw = raw_state.get("loaded_skills", [])

        try:
            loaded_skills = self.agent_config.normalize_loaded_skills(loaded_skills_raw, runtime)
        except ValueError as e:
            self.logger.warning("Invalid loaded_skills in state, resetting to base mode: %s", e)
            loaded_skills = []

        return {
            "loaded_skills": loaded_skills,
            "skill_switch_loop": raw_state.get("skill_switch_loop", -1),
            "skill_history": raw_state.get("skill_history", []),
        }

    def _get_or_create_manager(
        self, runtime: "AgentRuntimeContext", db_session: AsyncSession
    ) -> ConversationMemoryManager:
        """Create a new ConversationMemoryManager for each request.

        No caching is used to avoid concurrency issues in multi-tenant scenarios.
        Each request gets a fresh manager instance scoped to its thread_id.

        Args:
            runtime: Runtime context with thread_id, tenant, user info
            db_session: Database session for message operations

        Returns:
            ConversationMemoryManager instance
        """
        return ConversationMemoryManager(
            db_session=db_session,
            thread_id=runtime.thread_id,
            tenant_id=runtime.user.tenant_id,
            agent_id=self.agent_config.agent_id,
        )

    async def _load_history(self, state: AgentState, config: RunnableConfig) -> dict:
        """Load conversation history from database (first node in graph).

        Multi-layer context loading:
        1. Parent context (if sub-agent)
        2. Thread summaries
        3. Session summaries
        4. Recent messages
        5. Current messages

        Args:
            state: Current agent state with new user message
            config: Runtime configuration with thread_id and db_session

        Returns:
            State update with merged messages
        """
        from langchain_core.messages import SystemMessage

        runtime = extract_runtime_context(config)
        db_session = config.get("configurable", {}).get("db_session")
        manager = self._get_or_create_manager(runtime, db_session)
        context_messages = []

        # ============================================
        # Layer 1: Parent Context (if sub-agent)
        # ============================================
        parent_context = config.get("configurable", {}).get("parent_context")
        if parent_context and parent_context.get("summary"):
            context_messages.append(
                SystemMessage(
                    content=f"# Parent Conversation Context\n\n{parent_context['summary']}",
                    additional_kwargs={
                        "context_type": "parent_context",
                        "parent_thread_id": parent_context.get("thread_id"),
                    },
                )
            )
            self.logger.debug(f"Loaded parent context for agent {self.agent_config.agent_name}")

        # ============================================
        # Layer 2, 3 & 4: Thread Summaries + Session Summaries + Recent Messages
        # ============================================
        history_message_limit = config.get("configurable", {}).get("history_message_limit", 1)
        # load_messages_with_summary now loads all historical context in one call
        historical_messages = await manager.load_messages_with_summary(
            thread_summary_limit=1,  # Load 1 most recent thread summaries
            session_summary_limit=2,  # Load 2 most recent session summaries
            message_limit=history_message_limit,  # Load recent messages dynamically
        )

        if db_session:
            from apps.tenant_app_service.hitl.history import hydrate_hitl_history_messages

            historical_messages = await hydrate_hitl_history_messages(
                historical_messages,
                tenant_id=runtime.tenant.tenant_id,
                db=db_session,
            )

        # HITL resume: rewrite the approved/rejected ToolMessage for this turn only.
        hitl_resume = config.get("configurable", {}).get("hitl_resume")
        if hitl_resume:
            historical_messages = self._transform_hitl_history(historical_messages, hitl_resume)
            self.logger.info(
                "HITL resume history transformation applied for proposal_id=%s, action=%s",
                hitl_resume.get("proposal_id"),
                hitl_resume.get("action"),
            )

        context_messages.extend(historical_messages)

        # ============================================
        # Layer 5: Current Messages
        # ============================================
        current_messages = state.get("messages", [])
        combined = context_messages + current_messages

        self.logger.info(
            f"Loaded context for thread {runtime.thread_id}: "
            f"parent_context={bool(parent_context)}, "
            f"historical={len(historical_messages)}, "
            f"current={len(current_messages)}"
        )

        return {"messages": combined}

    def _transform_hitl_history(
        self,
        messages: List[BaseMessage],
        hitl_resume: dict,
    ) -> List[BaseMessage]:
        """Replace the stale gate ToolMessage with an approve-resume signal for the LLM."""
        from apps.tenant_app_service.hitl.domain import HITL_STATUS_APPROVED
        from apps.tenant_app_service.hitl.history import build_hydrated_hitl_tool_message

        proposal_id = hitl_resume.get("proposal_id")
        action = hitl_resume.get("action")

        if not proposal_id or action != HITL_STATUS_APPROVED:
            return messages

        result: List[BaseMessage] = []
        for msg in messages:
            if isinstance(msg, ToolMessage) and is_hitl_approval_request(msg, proposal_id):
                tool_name = (msg.additional_kwargs or {}).get("tool_name") or "tool"
                result.append(
                    build_hydrated_hitl_tool_message(
                        msg,
                        status=HITL_STATUS_APPROVED,
                        proposal_id=proposal_id,
                        tool_name=tool_name,
                    )
                )
                self.logger.info(
                    "Replaced HITL gate ToolMessage with approve-resume signal for proposal_id=%s",
                    proposal_id,
                )
            else:
                result.append(msg)

        return result

    def _prepare_system_messages(
        self,
        runtime: AgentRuntimeContext,
        loop_count: int,
        loaded_skills: list[str],
    ) -> List[SystemMessage]:
        """Prepare system messages for LLM call.

        Args:
            runtime: Runtime context with tenant, user, agent info
            loop_count: Current iteration count

        Returns:
            List of system messages (ephemeral, not saved to state)
        """
        # 1. Dynamic: system prompt scoped to tenant/user
        full_prompt = self.agent_config.get_system_prompt(loaded_skills, runtime)
        system_messages: list[SystemMessage] = []
        if full_prompt:
            system_messages.append(SystemMessage(content=full_prompt))

        # Inject runtime user preference context to reduce timezone ambiguity in scheduling tasks.
        if runtime.user.timezone_iana:
            system_messages.append(
                SystemMessage(
                    content=(
                        "## Runtime User Preferences\n"
                        f"- timezone_iana: {runtime.user.timezone_iana}\n"
                        "- Interpret user mentioned times in this timezone unless user explicitly overrides.\n"
                        "- For cron scheduling, cron fields are local time in timezone_iana "
                        "(do NOT convert cron fields to UTC manually)."
                    )
                )
            )

        # Add iteration warning if approaching limit
        if loop_count >= self.agent_config.max_loop_iterations:
            warning_msg = (
                "⚠️ You have reached the maximum number of iterations. "
                "Please provide a final answer based on the information gathered so far. "
                "Only call tools again if absolutely necessary."
            )
            self.logger.warning(warning_msg)
            system_messages.append(SystemMessage(content=warning_msg))

        return system_messages

    async def _llm_call(self, state: AgentState, config: RunnableConfig) -> dict:
        """Call the LLM with automatic stats tracking and message management.

        This method handles:
        - Pre-LLM summarization for context window control (via hook)
        - System prompt injection (ephemeral)
        - Stats tracking via V3 context managers
        - Loop limit warnings
        - Skill switch detection and model rebuild

        Args:
            state: Current agent state
            config: Runtime configuration

        Returns:
            Updated state with LLM response and stats
        """
        loop_count = state.get("loop_count", 0)
        tool_call_counts = state.get("tool_call_counts", {})
        runtime = extract_runtime_context(config)
        skill_state = self._get_skill_state(state, runtime)
        loaded_skills = skill_state.get("loaded_skills", [])
        current_messages = state["messages"]

        # init the vars incase exception happens
        start_time = time.time()
        messages = []
        removed_message_ids = set()
        try:  # catch the entire llm processing to ensure errors can be save into the message
            system_messages = self._prepare_system_messages(runtime, loop_count, loaded_skills)
            # Prepare messages for LLM: sanitize + compress via MessagePreparer
            messages, removed_message_ids, prompt_context_stats = await self.message_preparer.prepare_for_llm(
                current_messages, system_messages, config
            )
            self.logger.info("Prompt context stats: %s", asdict(prompt_context_stats))
            model_key = self.agent_config.model_key()

            # Update tenant config for tenant-scoped LLM usage
            tenant_config = runtime.tenant.config if runtime.tenant else None
            self._model_binding_manager.update_tenant_config(tenant_config)

            # Resolve tools at runtime for tenant-scoped skills
            tools = self.agent_config.get_tools(loaded_skills, runtime)

            model_with_tools = self._model_binding_manager.get_or_create(
                model_key=model_key,
                loaded_skills=loaded_skills,
                tools=tools,
            )

            response = None
            configured_model_id = self._model_binding_manager.get_configured_model_id()
            max_output_tokens = self._model_binding_manager.get_max_output_tokens()
            async with llm_call_tracker(
                model_key,
                runtime,
                prompt_context_stats=prompt_context_stats,
                configured_model_id=configured_model_id,
                max_output_tokens=max_output_tokens,
            ) as tracker:
                # Force non-streaming so usage reflects one API response (not summed stream chunks).
                response = await model_with_tools.ainvoke(messages, config=config, stream=False)
                if response:
                    response = ensure_visible_ai_content(response)
                tracker.record_response(response)
        except Exception as exc:
            self.logger.error("LLM call failed for agent %s: %s", self.agent_config.agent_name, exc, exc_info=True)
            response = AIMessage(
                id=str(uuid4()),
                content=f"⚠️ LLM call failed: {exc}",
                additional_kwargs={
                    "timestamp": datetime.now(UTC).isoformat(),
                    "error": True,
                },
            )

        duration_ms = (time.time() - start_time) * 1000
        skill_info = f"(loaded_skills={loaded_skills})"
        self.logger.info(
            f"LLM call completed for agent {self.agent_config.agent_name} {skill_info}"
            f"with {len(messages)} messages (iteration {loop_count}, tool usage: {tool_call_counts}, duration: {duration_ms:.2f}ms)"
        )

        # Add timestamp & session_id to AI response for tracking
        if response:
            response.additional_kwargs.setdefault("timestamp", datetime.now(UTC).isoformat())

        # Build state update - return complete message list
        # Remove sanitized messages and add new response
        new_messages = [msg for msg in current_messages if msg.id not in removed_message_ids]
        new_messages.append(response)

        state_update = {
            "messages": new_messages,
            "loop_count": loop_count + 1,
            "skill_state": skill_state,
        }
        return state_update

    async def _tool_node(self, state: AgentState, config: RunnableConfig) -> dict:
        last = state["messages"][-1]
        tool_calls = getattr(last, "tool_calls", None)
        results = []
        runtime = extract_runtime_context(config)
        tenant_info = f"{runtime.user.tenant_name} (ID: {runtime.user.tenant_id})"
        tool_call_counts = state.get("tool_call_counts", {}).copy()
        tool_cache = state.get("tool_cache", {}).copy()
        hitl_blocked = False
        skill_state = self._get_skill_state(state, runtime)
        loaded_skills = skill_state.get("loaded_skills", [])

        if tool_calls:
            skill_info = f"(loaded_skills={loaded_skills})"
            self.logger.info(f"Executing {len(tool_calls)} tool calls for tenant {tenant_info} {skill_info}")

            for idx, call in enumerate(tool_calls):
                tool_name = call["name"]

                # Handle skill control tools in framework state before next llm_call.
                if self.agent_config.has_skills(runtime) and tool_name in {
                    "load_skill",
                    "unload_skill",
                }:
                    tool_call_id = call["id"]
                    tool_args = call.get("args", {})
                    reason = tool_args.get("reason", "")

                    additional_kwargs = {
                        "timestamp": datetime.now(UTC).isoformat(),
                    }

                    available_skills = self.agent_config.get_resolved_skills(runtime)

                    if tool_name == "load_skill":
                        skill_name = tool_args.get("skill_name")
                        skill = available_skills.get(skill_name)
                        if skill_name in available_skills:
                            if skill_name not in loaded_skills:
                                loaded_skills.append(skill_name)
                            content = (
                                f"Loaded skill '{skill_name}' (scope: {skill.scope}). "
                                f"Skill scripts are at {skill.locator.container_skill_dir}/. "
                                f"Its prompt and tools will be merged into the next LLM iteration."
                            )
                        else:
                            error_msg = f"Invalid skill: {skill_name}. Available skills: {list(available_skills)}"
                            self.logger.warning(error_msg)
                            results.append(
                                ToolMessage(
                                    id=str(uuid4()),
                                    content=error_msg,
                                    tool_call_id=tool_call_id,
                                    additional_kwargs=additional_kwargs,
                                )
                            )
                            continue
                    elif tool_name == "unload_skill":
                        skill_name = tool_args.get("skill_name")
                        if skill_name in loaded_skills:
                            loaded_skills = [skill for skill in loaded_skills if skill != skill_name]
                            content = f"Unloaded skill: {skill_name}"
                        else:
                            content = f"Skill '{skill_name}' is not loaded."

                    self.logger.info(
                        "Skill state update requested via %s: loaded_skills=%s (reason=%s)",
                        tool_name,
                        loaded_skills,
                        reason,
                    )
                    results.append(
                        ToolMessage(
                            id=str(uuid4()),
                            content=content,
                            tool_call_id=tool_call_id,
                            additional_kwargs=additional_kwargs,
                        )
                    )

                    skill_state["loaded_skills"] = loaded_skills
                    skill_state["skill_switch_loop"] = state.get("loop_count", 0)
                    skill_history = skill_state.get("skill_history", [])
                    skill_history.append(
                        {
                            "action": tool_name,
                            "loaded_skills": loaded_skills,
                            "loop": state.get("loop_count", 0),
                            "reason": reason,
                        }
                    )
                    skill_state["skill_history"] = skill_history

                    # Keep executing remaining tool calls in this batch with the updated skill state.
                    continue

                # Regular tool execution
                tool_message, tool_call_counts, tool_cache = await self.tool_executor.execute_single_tool(
                    call,
                    tool_call_counts,
                    config,
                    loaded_skills=loaded_skills,
                    tool_cache=tool_cache,
                )
                results.append(tool_message)

                if self._handle_hitl_pause(tool_message=tool_message, tool_calls=tool_calls, idx=idx, results=results):
                    hitl_blocked = True
                    break

        state_update = {
            "messages": state.get("messages", []) + results,
            "tool_call_counts": tool_call_counts,
            "tool_cache": tool_cache,
            "skill_state": skill_state,
            "hitl_blocked": hitl_blocked,
        }
        return state_update

    def _handle_hitl_pause(
        self,
        *,
        tool_message: ToolMessage,
        tool_calls: list[dict],
        idx: int,
        results: list[ToolMessage],
    ) -> bool:
        """Handle HITL approval-request pause behavior for remaining tool calls.

        Returns:
            True if HITL pending is detected and remaining tool calls are skipped.
        """
        if not is_hitl_approval_request(tool_message):
            return False

        hitl_payload = tool_message.additional_kwargs.get("hitl", {})
        self.logger.info(
            "HITL approval requested for proposal_id=%s, pausing remaining tool calls",
            hitl_payload.get("proposal_id"),
        )

        additional_kwargs = {
            "timestamp": datetime.now(UTC).isoformat(),
        }
        for remaining_call in tool_calls[idx + 1 :]:
            results.append(
                ToolMessage(
                    id=str(uuid4()),
                    content="Skipped: Waiting for HITL approval",
                    tool_call_id=remaining_call["id"],
                    additional_kwargs=additional_kwargs,
                )
            )

        return True

    def _after_tool_node(self, state: AgentState) -> Literal["llm_call", "save_messages"]:
        """Route after tool execution.

        If HITL is pending, persist messages and stop current run so frontend can
        trigger approve continuation.
        """
        if state.get("hitl_blocked"):
            self.logger.info("HITL pending detected, ending current run and waiting for continuation")
            return "save_messages"
        return "llm_call"

    async def _save_messages(self, state: AgentState, config: RunnableConfig) -> dict:
        """Save all unsaved messages to database (executed after loop completes).

        This node saves all messages from state["messages"].
        The ConversationMemoryManager handles deduplication by message ID.

        Note: state["messages"] only contains conversation messages (not ephemeral system prompts).
        Ephemeral system prompts are created in _prepare_messages and never added to state.

        Args:
            state: Current agent state
            config: Runtime configuration

        Returns:
            Empty dict (no state update needed)
        """
        runtime = extract_runtime_context(config)
        db_session = config.get("configurable", {}).get("db_session")
        # Get or create manager for this thread
        manager = self._get_or_create_manager(runtime, db_session)

        # Get all messages from state
        messages_to_save = state.get("messages", [])

        if messages_to_save:
            await manager.add_messages(messages_to_save, config, deduplicate=True)

        return {}

    def _should_continue(self, state: AgentState) -> Literal["tool_node", "save_messages"]:
        """Determine if the agent should continue to tool execution or end.

        Stop conditions:
        1. No tool calls in last message (LLM decided to stop)
        2. Exceeded maximum iterations (force stop)

        Args:
            state: Current agent state

        Returns:
            Next node to execute: "tool_node" or "save_messages"
        """
        last_message = state["messages"][-1]
        loop_count = state.get("loop_count", 0)
        tool_call_counts = state.get("tool_call_counts", {})
        has_tool_calls = getattr(last_message, "tool_calls", None)

        # Determine stop reason
        exceeded_max_iterations = loop_count > self.agent_config.max_loop_iterations
        natural_stop = not has_tool_calls

        # Continue to tool execution if not stopping
        if not exceeded_max_iterations and not natural_stop:
            self.logger.debug(
                f"Continuing to tool execution (iteration {loop_count + 1}), tool usage: {tool_call_counts}"
            )
            return "tool_node"

        # Log stop reason and proceed to save
        if exceeded_max_iterations:
            self.logger.warning(
                f"Agent {self.agent_config.agent_name} stopped (exceeded max iterations) after {loop_count} iterations"
            )
        else:
            self.logger.info(f"Agent {self.agent_config.agent_name} stopped naturally after {loop_count} iterations")

        return "save_messages"

    def build_graph(self) -> StateGraph:
        """Build the agent graph with integrated message management.

        Graph structure:
        START → load_history → llm_call ⇄ tool_node → save_messages → END

        Summarization is handled within llm_call node before LLM invocation.

        Subclasses can override this to customize the graph structure.

        Returns:
            StateGraph instance (not compiled)
        """
        graph = StateGraph(AgentState)

        # Add nodes
        graph.add_node("load_history", self._load_history)
        graph.add_node("llm_call", self._llm_call)
        graph.add_node("tool_node", self._tool_node)
        graph.add_node("save_messages", self._save_messages)

        # Define edges
        graph.add_edge(START, "load_history")
        graph.add_edge("load_history", "llm_call")
        graph.add_conditional_edges("llm_call", self._should_continue, ["tool_node", "save_messages"])
        graph.add_conditional_edges("tool_node", self._after_tool_node, ["llm_call", "save_messages"])
        graph.add_edge("save_messages", END)

        return graph

    async def compile(self):
        """Compile the agent graph into an executable agent.

        The graph includes integrated message management (load/save/summarize).

        Returns:
            Compiled agent ready for invocation
        """
        graph = self.build_graph()
        return graph.compile(name=self.agent_config.agent_name)
