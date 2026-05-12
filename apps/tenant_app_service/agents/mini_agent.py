"""MiniAgent service - Stateless LLM capabilities.

Each method is a self-contained capability that requires AgentRuntimeContext.
Can be called from:
1. Backend services (create context explicitly)
2. Agent workflows (extract context from RunnableConfig)
3. REST API endpoints (create context from user/request data)
"""

from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.core import TenantAwareService
from apps.shared.utils.logger import get_logger
from apps.tenant_app_service.agents.domain import AgentRuntimeContext, AgentUserContext
from apps.tenant_app_service.agents.mini import MiniAgentConfig, MiniAgentExecutor
from apps.tenant_app_service.agents.system_agent_config import get_config_loader
from apps.tenant_app_service.chat.domain import MessageDomain
from apps.tenant_app_service.tenant.domain import TenantDomain
from apps.tenant_app_service.tenant.repository import TenantRepository

logger = get_logger(__name__)


class MiniAgentService(TenantAwareService):
    """High-level service for mini-agent operations.

    Design:
    - Black box: users provide data, not prompts
    - Context-aware: requires AgentRuntimeContext for all operations
    - Observable: all calls tracked for accounting and billing
    - Prompt engineering: service builds prompts from business data

    All methods require AgentRuntimeContext as the first parameter after
    business data. Callers are responsible for creating/extracting context.
    """

    def __init__(
        self,
        db: AsyncSession,
        tenant_id: int,
    ):
        """Initialize service.

        Args:
            db: Database session
            tenant_id: Tenant ID for isolation
            executor: Optional custom executor (for testing)
        """
        super().__init__(tenant_id=tenant_id, db_session=db)
        self.db = db
        self.executor = MiniAgentExecutor(db)
        self.logger = logger
        self._tenant_repo = TenantRepository(db)

    async def get_current_tenant(self) -> TenantDomain:
        """Get current tenant domain model.

        Returns:
            TenantDomain for the current tenant_id

        Raises:
            ValueError: If tenant not found
        """
        tenant = await self._tenant_repo.get_by_id(self.tenant_id)
        if not tenant:
            raise ValueError(f"Tenant not found: {self.tenant_id}")
        return tenant

    @classmethod
    def create(cls, db: AsyncSession, tenant_id: int) -> "MiniAgentService":
        """Factory method to create service.

        Args:
            db: Database session
            tenant_id: Tenant ID

        Returns:
            MiniAgentService instance
        """
        return cls(db, tenant_id)

    async def common_llm_call(
        self, agent_name: str, user_prompt: str, thread_id: str = None, session_id: str = None
    ) -> str:
        """Common method to call LLM with given agent name and user prompt.

        Args:
            agent_name: Name of the mini-agent to use
            user_prompt: User prompt text
            thread_id: Optional thread ID
            session_id: Optional session ID

        Returns:
            LLM response content

        Raises:
            ValueError: If LLM call fails
        """
        # Get config from registry (includes agent_id and agent_name)
        loader = get_config_loader()
        mini_config = loader.create_mini_agent_config(agent_name=agent_name)
        runtime_context = await self._create_system_runtime_context(
            config=mini_config,
            thread_id=thread_id,
            session_id=session_id,
        )
        result = await self.executor.execute(config=mini_config, context=runtime_context, user_prompt=user_prompt)
        return result.content

    async def summarize_session(
        self,
        thread_id: str,
        session_id: str,
        messages: list[MessageDomain],
        max_messages: int = 50,
    ) -> str:
        """Summarize a chat session from raw conversation messages.

        Uses the full conversation history to allow the LLM to identify:
        - Natural conversation flow and user intent evolution
        - Problem-solving patterns and error recovery
        - Tools used and their outcomes
        - Key results and lessons learned

        Args:
            thread_id: Thread ID for tracking
            session_id: Session ID for tracking
            messages: List of MessageDomain objects representing the conversation
            max_messages: Maximum number of messages to include (default 50, truncates from end)

        Returns:
            Session summary capturing conversation flow, patterns, and insights

        Raises:
            ValueError: If summarization fails
        """
        # Truncate messages if too long (keep most recent)
        if len(messages) > max_messages:
            messages = messages[-max_messages:]
            logger.info(f"Truncated session messages from {len(messages)} to {max_messages} for summarization")

        # Format messages into conversation format
        conversation_lines = []
        for msg in messages:
            role = msg.role.upper()
            content = msg.content or ""

            # Include tool call information for AI messages
            if msg.tool_calls:
                tool_names = [tc.get("name", "unknown") for tc in msg.tool_calls]
                content += f" [Tools called: {', '.join(tool_names)}]"

            # Include tool result indicator
            if msg.role == "tool" and msg.tool_call_id:
                role = "TOOL_RESULT"

            conversation_lines.append(f"{role}: {content}")

        conversation_text = "\n".join(conversation_lines)

        # Build user prompt with raw conversation
        user_prompt = f"""Analyze this conversation session and create a concise summary:
{conversation_text}
"""

        # Get config from registry (includes agent_id and agent_name)
        loader = get_config_loader()
        mini_config = loader.create_mini_agent_config(agent_name="SessionSummarizer")
        runtime_context = await self._create_system_runtime_context(
            config=mini_config,
            thread_id=thread_id,
            session_id=session_id,
        )

        result = await self.executor.execute(config=mini_config, context=runtime_context, user_prompt=user_prompt)
        return result.content

    async def summarize_thread(
        self,
        thread_id: str,
        session_summaries: list[dict],
    ) -> str:
        """Summarize a conversation thread from multiple session summaries.

        Specialized method for creating thread-level summaries that capture
        the overall conversation theme and key accomplishments across sessions.

        Args:
            thread_id: Thread ID
            session_summaries: List of session summary dicts with keys:
                - session_id: ID of the session
                - summary: Text summary of the session

        Returns:
            Thread summary text

        Raises:
            ValueError: If summarization fails
        """
        # Format session summaries into user prompt
        summary_parts = [f"Session-{i}:  {s['summary']}" for i, s in enumerate(session_summaries, 1)]
        combined_text = "\n".join(summary_parts)
        user_prompt = f"""Create a concise thread-level summary based on these recent sessions:

{combined_text}

"""

        # Get config from registry (includes agent_id and agent_name)
        loader = get_config_loader()
        mini_config = loader.create_mini_agent_config(agent_name="ThreadSummarizer")
        runtime_context = await self._create_system_runtime_context(
            config=mini_config,
            thread_id=thread_id,
        )
        result = await self.executor.execute(config=mini_config, context=runtime_context, user_prompt=user_prompt)
        return result.content

    async def generate_table_metadata(
        self,
        table_name: str,
        columns: list[dict],
        sample_data: list[dict] | None = None,
    ) -> dict:
        """Generate metadata for a table schema.

        Args:
            table_name: Name of the table
            columns: List of column dicts with name and type
            context: Runtime context with user, agent, session info (required)
            sample_data: Optional sample rows

        Returns:
            Dict with table_description, column_descriptions, and suggested_tags

        Raises:
            ValueError: If generation fails
        """
        # Build user prompt from business data
        schema_text = f"Table: {table_name}\nColumns:\n"
        for col in columns:
            schema_text += f"  - {col['name']} ({col['type']})\n"

        if sample_data:
            schema_text += "\nSample Data:\n"
            schema_text += str(sample_data)

        user_prompt = f"""Analyze this database table and generate metadata:

{schema_text}

Provide:
1. A concise table description (1-2 sentences)
2. Description for each column
3. Suggested tags for categorization"""

        # Get config from registry (includes agent_id and agent_name)
        loader = get_config_loader()
        mini_config = loader.create_mini_agent_config(agent_name="TableMetadataGenerator")
        runtime_context = await self._create_system_runtime_context(
            config=mini_config,
        )
        result = await self.executor.execute(config=mini_config, context=runtime_context, user_prompt=user_prompt)
        return result.structured_data

    async def classify_content(
        self,
        content: str,
        categories: list[str],
    ) -> dict:
        """Classify content into predefined categories.

        Args:
            content: Content to classify
            categories: List of possible categories

        Returns:
            Dict with category, confidence, and reasoning

        Raises:
            ValueError: If classification fails
        """
        # Build user prompt from business data
        categories_str = ", ".join(categories)
        user_prompt = f"""Classify the following content into one of these categories: {categories_str}

Content:
{content}

Provide:
1. The category name
2. Confidence score (0.0 to 1.0)
3. Brief reasoning"""

        # Get config from registry (includes agent_id and agent_name)
        loader = get_config_loader()
        mini_config = loader.create_mini_agent_config(agent_name="ContentClassifier")
        runtime_context = await self._create_system_runtime_context(
            config=mini_config,
        )
        result = await self.executor.execute(config=mini_config, context=runtime_context, user_prompt=user_prompt)
        return result.structured_data

    async def summarize_tool_output(
        self,
        tool_output: str,
        thread_id: str | None = None,
        session_id: str | None = None,
    ) -> str:
        """Summarize large tool output for context window optimization.

        Args:
            tool_output: The raw tool output to summarize
            thread_id: Optional thread ID for tracking
            session_id: Optional session ID for tracking

        Returns:
            Concise summary of the tool output

        Raises:
            ValueError: If summarization fails
        """
        # Build user prompt with full tool output
        max_output_size = 4000  # ~4k tokens, safe for most models
        if len(tool_output) > max_output_size:
            tool_output_to_send = tool_output[:max_output_size] + "\n\n[... output truncated due to length ...]"
            logger.warning(f"Tool output exceeds {max_output_size} chars, truncating for summarization")
        else:
            tool_output_to_send = tool_output

        user_prompt = f"""Summarize the following tool output concisely, preserving key information and structure.

Output:
{tool_output_to_send}
"""

        # Get config from registry
        loader = get_config_loader()
        mini_config = loader.create_mini_agent_config(agent_name="ToolOutputSummarizer")
        runtime_context = await self._create_system_runtime_context(
            config=mini_config,
            thread_id=thread_id,
            session_id=session_id,
        )
        result = await self.executor.execute(config=mini_config, context=runtime_context, user_prompt=user_prompt)
        return result.content

    async def _create_system_runtime_context(
        self, config: MiniAgentConfig, thread_id: str | None = None, session_id: str | None = None
    ):
        """Create a system-level AgentRuntimeContext for background tasks.

        Args:
            config: MiniAgentConfig with agent details
            session_id: Session ID, optional but will create system session if missing
            thread_id: Thread ID, optional but will create system thread if missing

        Returns:
            AgentRuntimeContext with system user
        """
        from apps.tenant_app_service.agents.context import create_agent_runtime_tenant_context

        tenant = await self.get_current_tenant()
        tenant_ctx = create_agent_runtime_tenant_context(
            tenant_id=tenant.id,
            tenant_name=tenant.name,
            config=tenant.config or {},
        )
        return AgentRuntimeContext(
            tenant=tenant_ctx,
            user=AgentUserContext(
                user_id=0,  # System user
                username="system",
                role="system",
                tenant_id=self.tenant_id,
                tenant_name=tenant_ctx.tenant_name,
            ),
            thread_id=thread_id if thread_id else "system-thread",
            session_id=session_id if session_id else "system-session",
            agent_id=config.agent_id,
            agent_name=config.agent_name,
        )
