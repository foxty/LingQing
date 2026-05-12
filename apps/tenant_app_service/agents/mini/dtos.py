"""DTOs for mini-agent API endpoints."""

from pydantic import BaseModel, Field


class SummarizeTextRequest(BaseModel):
    """Request to summarize text."""

    text: str = Field(..., description="Text to summarize")
    max_length: int = Field(200, ge=50, le=1000, description="Maximum summary length")


class TableMetadataRequest(BaseModel):
    """Request to generate table metadata."""

    table_name: str = Field(..., description="Name of the table")
    columns: list[dict] = Field(..., description="Column definitions")
    sample_data: list[dict] | None = Field(None, description="Optional sample rows")


class ClassifyContentRequest(BaseModel):
    """Request to classify content."""

    content: str = Field(..., description="Content to classify")
    categories: list[str] = Field(..., description="Possible categories")


class MiniAgentResultDTO(BaseModel):
    """Response from mini-agent execution."""

    content: str | None = None
    structured_data: dict | None = None
    model_used: str | None = None
    token_usage: dict | None = None
    duration_ms: float | None = None
    success: bool = True
    error: str | None = None


class TableMetadataDTO(BaseModel):
    """Structured output for table metadata."""

    table_description: str
    column_descriptions: dict[str, str]
    suggested_tags: list[str]


class ClassificationDTO(BaseModel):
    """Structured output for content classification."""

    category: str
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str | None = None
