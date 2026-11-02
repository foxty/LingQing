"""In-run summary: compress the current run's older prefix only when the prompt is over budget."""

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.tools import BaseTool
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.utils.logger import get_logger
from apps.tenant_app_service.agents.memory.memory_budget import input_token_budget
from apps.tenant_app_service.agents.ports.agent_run_port import AgentRunPort
from apps.tenant_app_service.agents.token_counter import count_tokens

logger = get_logger(__name__)

_SUMMARY_TYPE = "agent_run_summary"
_FIELD_CHARS = 4_000


def older_tool_round_prefix(run_messages: list[BaseMessage]) -> tuple[list[BaseMessage], list[BaseMessage]]:
    """Split a run transcript so the latest tool round stays verbatim.

    Returns ``(prefix, tail)``. ``prefix`` is empty when there is no older tool round.
    """
    last_round_start: int | None = None
    for index, message in enumerate(run_messages):
        if isinstance(message, AIMessage) and message.tool_calls:
            last_round_start = index
    if last_round_start is None or last_round_start == 0:
        return [], list(run_messages)
    return list(run_messages[:last_round_start]), list(run_messages[last_round_start:])


def _last_human_index(messages: list[BaseMessage]) -> int:
    index = -1
    for position, message in enumerate(messages):
        if isinstance(message, HumanMessage):
            index = position
    return index


def _is_run_summary(message: BaseMessage) -> bool:
    return isinstance(message, SystemMessage) and (message.additional_kwargs or {}).get("summary_type") == _SUMMARY_TYPE


def split_history_and_run(messages: list[BaseMessage]) -> tuple[list[BaseMessage], list[BaseMessage]]:
    """History through the last human, and the current run without a prior in-run summary."""
    last_human = _last_human_index(messages)
    if last_human < 0:
        history: list[BaseMessage] = []
        run = list(messages)
    else:
        history = list(messages[: last_human + 1])
        run = list(messages[last_human + 1 :])
    run = [message for message in run if not _is_run_summary(message)]
    return history, run


def splice_run_summary(
    messages: list[BaseMessage],
    *,
    summary_text: str,
    cutoff_message_id: str | None,
) -> list[BaseMessage]:
    """Insert the in-run summary after the trigger human and drop the summarized prefix."""
    history, run = split_history_and_run(messages)
    if cutoff_message_id:
        cutoff_index = None
        for index, message in enumerate(run):
            if message.id == cutoff_message_id:
                cutoff_index = index
                break
        if cutoff_index is not None:
            run = run[cutoff_index + 1 :]
    summary = SystemMessage(
        content=f"# Current run summary\n\n{summary_text}",
        additional_kwargs={"summary_type": _SUMMARY_TYPE},
    )
    return history + [summary] + run


def _render_prefix(messages: list[BaseMessage]) -> str:
    lines: list[str] = []
    for message in messages:
        content = message.content if isinstance(message.content, str) else str(message.content)
        if len(content) > _FIELD_CHARS:
            content = content[:_FIELD_CHARS] + "..."
        role = message.type if hasattr(message, "type") else "message"
        if isinstance(message, AIMessage) and message.tool_calls:
            names = [call.get("name", "tool") for call in message.tool_calls if isinstance(call, dict)]
            if names:
                content = f"{content} [tools: {', '.join(names)}]"
        lines.append(f"{role}: {content}")
    return "\n".join(lines)


async def compact_prepared_messages(
    messages: list[BaseMessage],
    *,
    db: AsyncSession,
    tenant_id: int,
    thread_id: str,
    run_id: str,
    tools: list[BaseTool] | None = None,
    agent_run_port: AgentRunPort | None = None,
) -> list[BaseMessage]:
    """Apply an existing in-run summary, and extend it when the prompt is still over budget.

    The latest tool round is left intact. A summarizer failure keeps the already spliced view.
    """
    if agent_run_port is None:
        return messages
    context_port = agent_run_port
    try:
        existing = await context_port.get_in_run_summary(tenant_id, run_id)
        view = list(messages)
        if existing is not None:
            view = splice_run_summary(
                view,
                summary_text=existing.summary_text,
                cutoff_message_id=existing.cutoff_message_id,
            )
        if count_tokens(view, tools=tools) <= input_token_budget():
            return view

        history, run = split_history_and_run(view)
        prefix, _tail = older_tool_round_prefix(run)
        if not prefix or prefix[-1].id is None:
            logger.info("Run %s is over budget but has no older tool round to compress", run_id)
            return view

        previous = existing.summary_text if existing is not None else None
        summary_text = await agent_run_port.summarize_run_prefix(
            tenant_id=tenant_id,
            thread_id=thread_id,
            run_id=run_id,
            previous_summary=previous,
            prefix_text=_render_prefix(prefix),
        )
        if not summary_text:
            return view

        cutoff_message_id = str(prefix[-1].id)
        through_id = await context_port.resolve_run_message_db_id(cutoff_message_id, run_id)
        await context_port.upsert_in_run_summary(
            tenant_id=tenant_id,
            thread_id=thread_id,
            run_id=run_id,
            summary_text=summary_text,
            cutoff_message_id=cutoff_message_id,
            through_agent_run_message_id=through_id,
        )
        return splice_run_summary(
            history + run,
            summary_text=summary_text,
            cutoff_message_id=cutoff_message_id,
        )
    except Exception as exc:
        logger.warning("In-run summary skipped for run %s: %s", run_id, exc, exc_info=True)
        return messages
