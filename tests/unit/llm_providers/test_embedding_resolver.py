"""Unit tests for tenant embedding resolution."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.embeddings import Embeddings

from apps.shared.core.exceptions import ValidationError
from apps.shared.llm_providers.embedding_resolver import resolve_tenant_embeddings


@pytest.mark.asyncio
async def test_resolve_tenant_embeddings_raises_when_default_unset():
    db = MagicMock()
    with patch(
        "apps.shared.llm_providers.embedding_resolver.LLMProviderConfigService",
    ) as mock_service_cls:
        mock_service = MagicMock()
        mock_service.resolve_default_embedding_profile = AsyncMock(
            side_effect=ValidationError("Default embedding model profile is not configured")
        )
        mock_service_cls.return_value = mock_service

        with pytest.raises(ValidationError, match="embedding model profile"):
            await resolve_tenant_embeddings(tenant_id=1, db=db)


@pytest.mark.asyncio
async def test_resolve_tenant_embeddings_returns_client_when_configured():
    db = MagicMock()
    stub_embeddings = MagicMock(spec=Embeddings)
    resolved_config = MagicMock()

    with (
        patch(
            "apps.shared.llm_providers.embedding_resolver.LLMProviderConfigService",
        ) as mock_service_cls,
        patch(
            "apps.shared.llm_providers.embedding_resolver.create_embeddings",
            return_value=stub_embeddings,
        ) as mock_create,
    ):
        mock_service = MagicMock()
        mock_service.resolve_default_embedding_profile = AsyncMock(return_value=resolved_config)
        mock_service_cls.return_value = mock_service

        result = await resolve_tenant_embeddings(tenant_id=7, db=db)

    assert result is stub_embeddings
    mock_create.assert_called_once_with(resolved_config)
