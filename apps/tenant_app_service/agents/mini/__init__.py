"""Mini agents - Lightweight, stateless LLM operations.

Mini agents provide quick LLM capabilities without conversation state:
- Summarization
- Classification
- Metadata generation

Can be used in:
1. Agent workflows (via RunnableConfig)
2. Backend services
3. REST API endpoints
"""

from apps.tenant_app_service.agents.mini.domain import MiniAgentConfig, MiniAgentResult
from apps.tenant_app_service.agents.mini.dtos import (
    ClassificationDTO,
    ClassifyContentRequest,
    MiniAgentResultDTO,
    SummarizeTextRequest,
    TableMetadataDTO,
    TableMetadataRequest,
)
from apps.tenant_app_service.agents.mini.executor import MiniAgentExecutor

# Note: Import MiniAgentService from root to avoid circular imports:
# from apps.tenant_app_service.agents.mini_agent import MiniAgentService

__all__ = [
    "MiniAgentConfig",
    "MiniAgentResult",
    "MiniAgentExecutor",
    "SummarizeTextRequest",
    "TableMetadataRequest",
    "ClassifyContentRequest",
    "MiniAgentResultDTO",
    "TableMetadataDTO",
    "ClassificationDTO",
]
