"""Resolve tenant embedding clients from the LLM provider registry."""

from __future__ import annotations

from langchain_core.embeddings import Embeddings
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.infra.llm.llm_model_resolver import create_embeddings
from apps.shared.llm_providers.service import LLMProviderConfigService


async def resolve_tenant_embeddings(tenant_id: int, db: AsyncSession) -> Embeddings | None:
    """Return embeddings for the tenant default profile, or None when unset."""
    service = LLMProviderConfigService(tenant_id, db)
    defaults = await service.get_defaults()
    if defaults.embedding_profile_id is None:
        return None
    resolved = await service.resolve_profile(defaults.embedding_profile_id)
    return create_embeddings(resolved)
