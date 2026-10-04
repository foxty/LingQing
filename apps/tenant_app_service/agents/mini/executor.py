"""Core executor for stateless LLM calls.

Uses LangChain directly for model-agnostic execution without state management.
Metrics collection via agent_metrics_instrumentation for consistency.
"""

from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.infra.llm.llm_model_resolver import create_chat_model
from apps.shared.llm_providers.service import LLMProviderConfigService
from apps.shared.utils.logger import get_logger
from apps.tenant_app_service.agents.domain import AgentRuntimeContext
from apps.tenant_app_service.agents.metrics.agent_metrics_instrumentation import llm_call_tracker
from apps.tenant_app_service.agents.mini.domain import MiniAgentConfig, MiniAgentResult

logger = get_logger(__name__)


class MiniAgentExecutor:
    """Core executor for stateless LLM calls."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.logger = logger

    async def execute(self, config: MiniAgentConfig, context: AgentRuntimeContext, user_prompt: str) -> MiniAgentResult:
        if not context.tenant:
            raise ValueError("Tenant context not available for mini agent execution")

        service = LLMProviderConfigService(context.tenant.tenant_id, self.db)
        resolved = await service.resolve_default_llm_profile(mini=True)
        model_key = resolved.profile_name
        configured_model_id = resolved.model_id
        model = create_chat_model(resolved)

        messages = [
            SystemMessage(content=config.system_prompt),
            HumanMessage(content=user_prompt),
        ]

        max_retries = 3
        base_delay = 1.0

        for attempt in range(max_retries):
            try:
                if config.response_format:
                    model = model.with_structured_output(config.response_format)

                async with llm_call_tracker(
                    model_key,
                    context,
                    configured_model_id=configured_model_id,
                ) as tracker:
                    response = await model.ainvoke(messages, config={"tags": ["mini-agent"]})
                    tracker.record_response(response)
                    logger.debug(f"MiniAgent LLM response: {response}")

                    if config.response_format:
                        return MiniAgentResult(
                            structured_data=response.model_dump(),
                        )
                    return MiniAgentResult(
                        content=response.content if hasattr(response, "content") else str(response),
                    )

            except Exception as exc:
                if not self._is_transient_error(exc) or attempt == max_retries - 1:
                    logger.error(
                        "MiniAgent LLM call failed after %s attempts: %s",
                        attempt + 1,
                        exc,
                        exc_info=True,
                    )
                    raise
                delay = base_delay * (2**attempt)
                logger.warning(
                    "MiniAgent LLM call failed (attempt %s/%s), retrying in %ss: %s",
                    attempt + 1,
                    max_retries,
                    delay,
                    exc,
                )
                import asyncio

                await asyncio.sleep(delay)

        raise RuntimeError("MiniAgent execution failed unexpectedly")

    @staticmethod
    def _is_transient_error(exc: Exception) -> bool:
        message = str(exc).lower()
        transient_markers = (
            "429",
            "503",
            "504",
            "timeout",
            "rate limit",
            "too many requests",
            "service unavailable",
            "gateway timeout",
        )
        return any(marker in message for marker in transient_markers)
