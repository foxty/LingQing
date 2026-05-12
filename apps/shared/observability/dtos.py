"""DTOs for observability API responses."""

from datetime import datetime

from pydantic import BaseModel, Field


class TenantUsageStatsDTO(BaseModel):
    """Tenant usage statistics for observability and billing."""

    tenant_id: int
    period_start: datetime
    period_end: datetime

    # Call statistics
    total_llm_calls: int = Field(description="Total LLM API calls")
    total_llm_errors: int = Field(description="Total LLM call errors")
    total_tool_calls: int = Field(description="Total tool executions")
    total_tool_errors: int = Field(description="Total tool execution errors")

    # Token usage
    total_input_tokens: int = Field(description="Total input tokens consumed")
    total_output_tokens: int = Field(description="Total output tokens generated")
    total_tokens: int = Field(description="Total tokens (input + output)")

    # Session statistics
    unique_sessions: int = Field(description="Number of unique agent sessions")
    unique_threads: int = Field(description="Number of unique conversation threads")
    unique_users: int = Field(description="Number of unique users")

    # Cost estimation (future)
    estimated_cost: float | None = Field(default=None, description="Estimated cost in USD")


class AgentPerformanceDTO(BaseModel):
    """Agent performance metrics."""

    agent_id: int
    agent_name: str | None = None
    period_start: datetime
    period_end: datetime

    # Usage statistics
    total_sessions: int
    total_llm_calls: int
    total_tool_calls: int
    total_tokens: int

    # Performance metrics
    avg_session_duration_ms: float | None = None
    avg_llm_duration_ms: float | None = None
    avg_tool_duration_ms: float | None = None

    # Error rates
    llm_error_rate: float = Field(description="LLM error rate (0-1)")
    tool_error_rate: float = Field(description="Tool error rate (0-1)")
