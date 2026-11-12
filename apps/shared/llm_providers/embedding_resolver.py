"""Resolve tenant embedding clients from the LLM provider registry."""

from __future__ import annotations

from langchain_core.embeddings import Embeddings
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.infra.llm.llm_model_resolver import create_embeddings
from apps.shared.llm_providers.service import LLMProviderConfigService


async def resolve_tenant_embeddings(tenant_id: int, db: AsyncSession) -> Embeddings:
    """Return embeddings for the tenant default profile.

    Raises:
        ValidationError: When the tenant has no default embedding profile configured.
    """
    service = LLMProviderConfigService(tenant_id, db)
    resolved = await service.resolve_default_embedding_profile()
    return create_embeddings(resolved)
