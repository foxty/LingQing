"""Domain models for mini-agent operations.

Mini agents are stateless, single-purpose LLM calls with observability.
"""

from dataclasses import dataclass

from pydantic import BaseModel, Field

from apps.shared.domain.base_domain_model import BaseDomainModel


@dataclass
class MiniAgentResult(BaseDomainModel):
    """Result from a mini-agent execution.

    Contains only the operation result. Observability metrics (tokens, duration, model)
    are tracked separately by agent_metrics_instrumentation.
    Exceptions are raised directly; no error wrapping.
    """

    content: str | None = None  # Raw text response
    structured_data: dict | None = None  # Parsed Pydantic model as dict


@dataclass
class MiniAgentConfig(BaseDomainModel):
    """Configuration for mini-agent execution.

    Contains only common LLM parameters and processed prompts.
    Service layer is responsible for building prompts from business data.
    """

    agent_id: int
    agent_name: str
    system_prompt: str
    temperature: float | None = None
    max_tokens: int | None = None
    response_format: type | None = None  # Pydantic model for structured output


# Structured output schemas for specific mini-agent capabilities
# These remain as Pydantic models since they're output schemas for LLM responses


class TableMetadata(BaseModel):
    """Schema for table metadata generation."""

    table_description: str
    column_descriptions: dict[str, str]
    suggested_tags: list[str]


class Classification(BaseModel):
    """Schema for content classification."""

    category: str
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str | None = None
