"""Core executor for stateless LLM calls.

Uses LangChain directly for model-agnostic execution without state management.
Metrics collection via agent_metrics_instrumentation for consistency.
"""

from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.infra.llm.llm_model_factory import LLMModelFactory
from apps.shared.utils.logger import get_logger
from apps.tenant_app_service.agents.domain import AgentRuntimeContext
from apps.tenant_app_service.agents.metrics.agent_metrics_instrumentation import llm_call_tracker
from apps.tenant_app_service.agents.mini.domain import MiniAgentConfig, MiniAgentResult

logger = get_logger(__name__)


class MiniAgentExecutor:
    """Core executor for stateless LLM calls.

    Design:
    - Uses LangChain's ChatModel interface (model-agnostic)
    - No LangGraph/StateGraph (too heavy for single calls)
    - Automatic retry with exponential backoff
    - Integrated observability tracking
    - Dumb executor: just runs LLM with provided prompts
    - Supports tenant-scoped LLM config (mini_agent_model)
    """

    def __init__(self, db: AsyncSession):
        """Initialize executor.

        Args:
            db: Database session for metrics storage
        """
        self.db = db
        self.logger = logger

    async def execute(self, config: MiniAgentConfig, context: AgentRuntimeContext, user_prompt: str) -> MiniAgentResult:
        """Execute a single LLM call with observability and retry.

        Requires tenant LLM config to be configured.

        Args:
            config: MiniAgentConfig with prompts and parameters
            context: AgentRuntimeContext for tracking

        Returns:
            MiniAgentResult with response and metrics

        Raises:
            ValueError: If tenant LLM config is not configured
        """
        tenant_config = context.tenant.config if context.tenant else None
        if not tenant_config:
            raise ValueError("Tenant config not available for mini agent execution")

        model_factory = LLMModelFactory(tenant_config)
        if not model_factory.is_configured():
            raise ValueError(
                "Tenant LLM config not configured. Please configure LLM in tenant settings before using mini agents."
            )

        messages = [
            SystemMessage(content=config.system_prompt),
            HumanMessage(content=user_prompt),
        ]

        model_key = model_factory.get_model_name("mini_agent_model")
        configured_model_id = model_factory.get_mini_agent_model_id()
        max_retries = 3
        base_delay = 1.0

        for attempt in range(max_retries):
            try:
                model = model_factory.get_mini_agent_model()

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
                    else:
                        return MiniAgentResult(
                            content=response.content,
                        )
            except Exception as e:
                if attempt < max_retries - 1 and self._is_transient_error(e):
                    delay = base_delay * (2**attempt)
                    self.logger.warning(f"Transient error, retrying in {delay}s: {str(e)}")
                    continue
                else:
                    raise

    def _is_transient_error(self, error: Exception) -> bool:
        """Check if error is transient (should retry)."""
        error_str = str(error).lower()
        transient_indicators = [
            "429",  # Rate limit
            "503",  # Service unavailable
            "504",  # Gateway timeout
            "timeout",
            "timed out",
            "rate limit",
            "too many requests",
            "temporarily unavailable",
        ]
        return any(indicator in error_str for indicator in transient_indicators)
