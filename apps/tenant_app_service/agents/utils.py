from langchain_core.messages import (
    BaseMessage,
)


def gen_messages_desc(messages: list["BaseMessage"]) -> None:
    """Generate descriptions of messages for logging purposes."""
    desc_list = []
    for msg in messages:
        has_tool_calls = hasattr(msg, "tool_calls") and len(msg.tool_calls) > 0
        desc = f"{msg.__class__.__name__}(id={msg.id}, type={msg.type}, has_tool_calls={has_tool_calls}, content_length={len(str(msg.content))}, summary_type={msg.additional_kwargs.get('summary_type', 'N/A')})"
        desc_list.append(desc)

    return "\n".join(desc_list)
