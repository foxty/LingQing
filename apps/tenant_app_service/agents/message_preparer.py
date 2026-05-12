"""Message preparation for LLM calls.

This module handles all message processing before sending to LLM:
- Sanitization (remove incomplete tool call/result pairs)
- Compression (reduce context window usage for historical tool outputs)
- Long-lived tool output preservation across trim boundaries
- Preparation (combine system messages with conversation)
"""

from typing import List, NamedTuple

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig

from apps.shared.utils.logger import get_logger
from apps.tenant_app_service.agents.domain import RETENTION_LONG_LIVED, PromptContextStats

logger = get_logger(__name__)

TRANSIENT_COMPRESS_MAX_CHARS = 200


class CompressionAndPreservationResult(NamedTuple):
    """Typed result for _compress_and_preserve stage."""

    messages: List[BaseMessage]
    preserved_count: int
    preserved_chars: int
    compressed_count: int
    compressed_chars_saved: int


class MessagePreparer:
    """Handles message preparation for LLM calls.

    Responsibilities:
    - Sanitize messages (remove incomplete tool_call/tool_result pairs)
    - Trim messages to a fixed window to avoid context explosion
    - Prepare final message list for LLM invocation
    """

    def __init__(self, agent_name: str, max_messages: int = 50):
        """Initialize message preparer.

        Args:
            agent_name: Agent name for logging
            max_messages: Maximum number of conversation messages to keep.
                          Trimming preserves the most recent messages and never
                          splits an AIMessage/ToolMessage group. Defaults to 14.
        """
        self.logger = get_logger(__name__, agent_name)
        self.max_messages = max_messages

    @staticmethod
    def _message_char_len(message: BaseMessage) -> int:
        """Return character length of message content for observability stats."""
        content = getattr(message, "content", "")
        return len(content) if isinstance(content, str) else len(str(content))

    def sanitize_messages(self, messages: List[BaseMessage]) -> tuple[List[BaseMessage], List[str]]:
        """Remove incomplete tool_call/tool_result pairs to prevent LLM API errors.

        Anthropic/Claude requires that every AIMessage with tool_calls must be followed
        by corresponding ToolMessages. This can be violated if a previous conversation
        was interrupted mid-execution.

        Args:
            messages: List of messages to sanitize

        Returns:
            Tuple of (sanitized_messages, removed_ids):
            - sanitized_messages: Clean message list safe for LLM
            - removed_ids: IDs of messages that were removed
        """
        if not messages:
            return messages, []

        result = []
        removed_ids = []
        i = 0

        while i < len(messages):
            msg = messages[i]

            # Check if this is an AIMessage with tool_calls
            if isinstance(msg, AIMessage) and msg.tool_calls:
                tool_call_ids = {tc["id"] for tc in msg.tool_calls}

                # Scan forward to find corresponding ToolMessages
                # ToolMessages must immediately follow the AIMessage (only other ToolMessages in between)
                j = i + 1
                tool_messages = []
                while j < len(messages):
                    next_msg = messages[j]
                    if isinstance(next_msg, ToolMessage):
                        if next_msg.tool_call_id in tool_call_ids:
                            tool_messages.append(next_msg)
                            tool_call_ids.discard(next_msg.tool_call_id)
                        j += 1
                    else:
                        # Hit a non-ToolMessage, stop collecting
                        break

                # Only include if ALL tool_calls have results
                if not tool_call_ids:
                    # Complete group - add AIMessage and its ToolMessages
                    result.append(msg)
                    result.extend(tool_messages)
                else:
                    # Incomplete group - skip the AIMessage and any partial ToolMessages
                    self.logger.warning(
                        f"Removing incomplete AIMessage({msg.id}) with {len(tool_call_ids)} missing tool_results "
                        f"(tool_call_ids: {tool_call_ids})"
                    )
                    removed_ids.append(msg.id)
                    removed_ids.extend([tm.id for tm in tool_messages])

                i = j

            elif isinstance(msg, ToolMessage):
                # Check if this ToolMessage has a corresponding AIMessage already in result
                has_parent = any(
                    isinstance(m, AIMessage)
                    and m.tool_calls
                    and any(tc["id"] == msg.tool_call_id for tc in m.tool_calls)
                    for m in result
                )

                if not has_parent:
                    # Orphaned ToolMessage - skip it
                    self.logger.warning(
                        f"Removing orphaned ToolMessage (message_id:{msg.id}, tool_call_id: {msg.tool_call_id})"
                    )
                    removed_ids.append(msg.id)
                # If has_parent, it was already added to result in the AIMessage block

                i += 1

            else:
                # Regular message - add it
                result.append(msg)
                i += 1

        if removed_ids:
            self.logger.info(f"Sanitized {len(removed_ids)} incomplete/orphaned tool messages")

        return result, removed_ids

    @staticmethod
    def _build_groups(messages: List[BaseMessage]) -> List[List[BaseMessage]]:
        """Build atomic message groups (AIMessage + its ToolMessages stay together)."""
        groups: List[List[BaseMessage]] = []
        i = 0
        while i < len(messages):
            msg = messages[i]
            if isinstance(msg, AIMessage) and msg.tool_calls:
                tool_call_ids = {tc["id"] for tc in msg.tool_calls}
                group: List[BaseMessage] = [msg]
                i += 1
                while i < len(messages) and isinstance(messages[i], ToolMessage):
                    if messages[i].tool_call_id in tool_call_ids:
                        group.append(messages[i])
                    i += 1
                groups.append(group)
            else:
                groups.append([msg])
                i += 1
        return groups

    def trim_messages(self, messages: List[BaseMessage]) -> tuple[List[BaseMessage], List[List[BaseMessage]]]:
        """Trim messages to at most ``max_messages``, keeping the most recent ones.

        AIMessage/ToolMessage groups are treated as atomic units.
        Guarantees at least one HumanMessage is preserved to satisfy LLM API
        requirements (some providers reject requests without a user-role message).

        Returns:
            Tuple of (kept_messages, dropped_groups).
        """
        if len(messages) <= self.max_messages:
            return messages, []

        groups = self._build_groups(messages)

        # Accumulate most-recent groups from the end.
        kept_count = 0
        total = 0
        for group in reversed(groups):
            if total + len(group) <= self.max_messages:
                kept_count += 1
                total += len(group)
            else:
                break

        split = len(groups) - kept_count
        dropped = groups[:split]
        kept = groups[split:]

        # Guarantee at least one HumanMessage survives trimming.
        has_human = any(isinstance(m, HumanMessage) for g in kept for m in g)
        if not has_human:
            for i in range(len(dropped) - 1, -1, -1):
                if any(isinstance(m, HumanMessage) for m in dropped[i]):
                    kept = [dropped[i]] + kept
                    dropped = dropped[:i] + dropped[i + 1 :]
                    self.logger.info("Re-included most recent HumanMessage group to satisfy LLM user-role requirement")
                    break

        result = [msg for group in kept for msg in group]
        self.logger.info(
            f"Trimmed {len(messages) - len(result)} messages from conversation history "
            f"(kept {len(result)}/{len(messages)}, max_messages={self.max_messages})"
        )
        return result, dropped

    def _compress_and_preserve(
        self,
        kept_messages: List[BaseMessage],
        dropped_groups: List[List[BaseMessage]],
    ) -> CompressionAndPreservationResult:
        """Preserve long-lived tool outputs and compress transient ones.

        For dropped groups containing long-lived ToolMessages, convert them to
        compact SystemMessages prepended before kept messages.
        For kept transient ToolMessages older than the last HumanMessage,
        truncate their content.

        All transforms are LLM-view-only; stored messages remain intact.
        """
        preserved_sections: List[str] = []
        preserved_count = 0
        preserved_chars = 0

        # 1. Extract long-lived tool outputs from dropped groups
        for group in dropped_groups:
            for msg in group:
                if not isinstance(msg, ToolMessage):
                    continue
                retention = (msg.additional_kwargs or {}).get("result_retention")
                if retention != RETENTION_LONG_LIVED:
                    continue
                tool_name = (msg.additional_kwargs or {}).get("tool_name", "unknown_tool")
                preserved_sections.append(f"## {tool_name}\n\n{msg.content}")
                preserved_count += 1
                preserved_chars += self._message_char_len(msg)

        # 2. Compress transient tool outputs in kept messages that are older
        #    than the last HumanMessage (i.e. no longer the "active" cycle).
        last_human_idx = -1
        for i, msg in enumerate(kept_messages):
            if isinstance(msg, HumanMessage):
                last_human_idx = i

        compressed_messages: List[BaseMessage] = []
        compressed_count = 0
        compressed_chars_saved = 0
        for i, msg in enumerate(kept_messages):
            if isinstance(msg, ToolMessage) and i < last_human_idx and len(msg.content) > TRANSIENT_COMPRESS_MAX_CHARS:
                retention = (msg.additional_kwargs or {}).get("result_retention")
                if retention != RETENTION_LONG_LIVED:
                    truncated_content = msg.content[:TRANSIENT_COMPRESS_MAX_CHARS] + "\n... [truncated]"
                    compressed_count += 1
                    compressed_chars_saved += max(0, len(msg.content) - len(truncated_content))
                    compressed_messages.append(
                        ToolMessage(
                            id=msg.id,
                            content=truncated_content,
                            tool_call_id=msg.tool_call_id,
                            additional_kwargs=msg.additional_kwargs,
                        )
                    )
                    continue
            compressed_messages.append(msg)

        prefix: List[BaseMessage] = []
        if preserved_sections:
            self.logger.info(f"Preserved {len(preserved_sections)} long-lived tool output(s) from trimmed messages")
            prefix.append(
                SystemMessage(
                    content="# Preserved Tool Outputs\n\n" + "\n\n".join(preserved_sections),
                    additional_kwargs={"preserved_from": "long_lived_tool_output"},
                )
            )

        return CompressionAndPreservationResult(
            messages=prefix + compressed_messages,
            preserved_count=preserved_count,
            preserved_chars=preserved_chars,
            compressed_count=compressed_count,
            compressed_chars_saved=compressed_chars_saved,
        )

    async def prepare_for_llm(
        self,
        conversation_messages: List[BaseMessage],
        system_messages: List[SystemMessage],
        config: RunnableConfig,
    ) -> tuple[List[BaseMessage], set[str], PromptContextStats]:
        """Prepare complete message list for LLM call and identify messages to remove.

        Pipeline:
        1. Sanitize (remove incomplete tool_call/tool_result pairs)
        2. Trim to fixed window
        3. Compress transient tool outputs + preserve long-lived ones
        4. Prepend system messages

        State and database always store original complete messages.

        Returns:
            Tuple of (messages_for_llm, removed_message_ids, prompt_context_stats)
        """
        original_count = len(conversation_messages)
        sanitized_messages, sanitized_ids = self.sanitize_messages(conversation_messages)
        sanitized_id_set = set(sanitized_ids)
        sanitized_chars = sum(
            self._message_char_len(msg) for msg in conversation_messages if msg.id in sanitized_id_set
        )

        trimmed_messages, dropped_groups = self.trim_messages(sanitized_messages)
        trimmed_count = len(sanitized_messages) - len(trimmed_messages)
        trimmed_chars = sum(self._message_char_len(msg) for group in dropped_groups for msg in group)

        compress_result = self._compress_and_preserve(trimmed_messages, dropped_groups)

        final_messages = system_messages + compress_result.messages
        prompt_context_stats = PromptContextStats(
            original_count=original_count,
            sanitized_count=len(sanitized_ids),
            sanitized_chars=sanitized_chars,
            trimmed_count=trimmed_count,
            trimmed_chars=trimmed_chars,
            preserved_long_lived=compress_result.preserved_count,
            preserved_chars=compress_result.preserved_chars,
            compressed_transient=compress_result.compressed_count,
            compressed_chars_saved=compress_result.compressed_chars_saved,
            final_count=len(final_messages),
        )

        return final_messages, sanitized_id_set, prompt_context_stats
