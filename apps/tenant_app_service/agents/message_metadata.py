"""Keys and helpers for chat message_metadata (not sent back to the LLM).

Producers (e.g. message_content, agent_base) may place these fields on
AIMessage.additional_kwargs; ConversationMemoryManager moves them into
message_metadata before persistence.
"""

from __future__ import annotations

from typing import Any

# General conversation / capability fields
GENERAL_MESSAGE_METADATA_KEYS = (
    "timestamp",
    "sub_agent_id",
    "capability_id",
    "capability_name",
)

# Reasoning / thinking (from extract_thinking_persistence_metadata in message_content)
THINKING_MESSAGE_METADATA_KEYS = (
    "thinking_content",
    "reasoning_tokens",
    "thinking_evidence",
    "thinking_content_blocks",
)

ALL_PERSISTED_METADATA_KEYS = GENERAL_MESSAGE_METADATA_KEYS + THINKING_MESSAGE_METADATA_KEYS


def pop_message_metadata_from_kwargs(kwargs: dict[str, Any]) -> dict[str, Any]:
    """Move persisted metadata keys from additional_kwargs into a metadata dict."""
    metadata: dict[str, Any] = {}
    for key in GENERAL_MESSAGE_METADATA_KEYS:
        if key in kwargs:
            metadata[key] = kwargs.pop(key)
    if "attached_artifacts" in kwargs:
        metadata["attached_artifacts"] = kwargs.pop("attached_artifacts")
    elif "context_resources" in kwargs:
        metadata["attached_artifacts"] = kwargs.pop("context_resources")
    for key in THINKING_MESSAGE_METADATA_KEYS:
        if key in kwargs:
            metadata[key] = kwargs.pop(key)
    return metadata
