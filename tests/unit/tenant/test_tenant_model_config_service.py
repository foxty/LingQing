"""Unit tests for TenantModelConfigService embedding model change detection."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.shared.schemas.model_config import ModelConfigDTO
from apps.shared.utils.field_cipher import FieldCipher
from apps.tenant_app_service.tenant.tenant_model_config_service import TenantModelConfigService


class TestEmbeddingModelChangeDetection:
    """Tests for _embedding_model_changed method."""

    def test_returns_true_when_no_existing_config(self):
        """New setup should return True (model changed from none to something)."""
        service = TenantModelConfigService(tenant_id=1)

        new_config_dict = {
            "embedding_config": {
                "embedding_model": {
                    "model_id": "text-embedding-3-small",
                    "api_base": "https://api.openai.com/v1",
                }
            }
        }

        result = service._embedding_model_changed({}, new_config_dict)
        assert result is True

    def test_returns_true_when_model_id_changes(self):
        """Model ID change should return True."""
        service = TenantModelConfigService(tenant_id=1)

        existing_embedding = {
            "model_id": "text-embedding-3-small",
            "api_base": "https://api.openai.com/v1",
        }

        new_config_dict = {
            "embedding_config": {
                "embedding_model": {
                    "model_id": "text-embedding-3-large",
                    "api_base": "https://api.openai.com/v1",
                }
            }
        }

        result = service._embedding_model_changed(existing_embedding, new_config_dict)
        assert result is True

    def test_returns_true_when_api_base_changes(self):
        """API base change should return True (different provider)."""
        service = TenantModelConfigService(tenant_id=1)

        existing_embedding = {
            "model_id": "text-embedding-3-small",
            "api_base": "https://api.openai.com/v1",
        }

        new_config_dict = {
            "embedding_config": {
                "embedding_model": {
                    "model_id": "text-embedding-3-small",
                    "api_base": "https://custom-embedding.example.com/v1",
                }
            }
        }

        result = service._embedding_model_changed(existing_embedding, new_config_dict)
        assert result is True

    def test_returns_false_when_model_unchanged(self):
        """Same model_id and api_base should return False."""
        service = TenantModelConfigService(tenant_id=1)

        existing_embedding = {
            "model_id": "text-embedding-3-small",
            "api_base": "https://api.openai.com/v1",
            "api_key": "encrypted-key",
        }

        new_config_dict = {
            "embedding_config": {
                "embedding_model": {
                    "model_id": "text-embedding-3-small",
                    "api_base": "https://api.openai.com/v1",
                    "api_key": "new-encrypted-key",
                }
            }
        }

        result = service._embedding_model_changed(existing_embedding, new_config_dict)
        assert result is False

    def test_returns_false_when_only_api_key_changes(self):
        """API key change alone should not trigger model change."""
        service = TenantModelConfigService(tenant_id=1)

        existing_embedding = {
            "model_id": "text-embedding-3-small",
            "api_base": "https://api.openai.com/v1",
            "api_key": "old-encrypted-key",
        }

        new_config_dict = {
            "embedding_config": {
                "embedding_model": {
                    "model_id": "text-embedding-3-small",
                    "api_base": "https://api.openai.com/v1",
                    "api_key": "new-encrypted-key",
                }
            }
        }

        result = service._embedding_model_changed(existing_embedding, new_config_dict)
        assert result is False


class TestMergeModelParams:
    """Tests for _merge_model_params helper."""

    def test_returns_existing_when_incoming_is_none(self):
        service = TenantModelConfigService(tenant_id=1)
        existing = {"temperature": 0.2, "max_tokens": 2000}

        result = service._merge_model_params(existing, None)

        assert result == existing

    def test_merges_incoming_over_existing(self):
        service = TenantModelConfigService(tenant_id=1)
        existing = {"temperature": 0.2, "max_tokens": 2000, "top_p": 0.9}

        result = service._merge_model_params(existing, {"temperature": 0.5, "max_tokens": 8000})

        assert result == {"temperature": 0.5, "max_tokens": 8000, "top_p": 0.9}

    def test_returns_incoming_when_no_existing(self):
        service = TenantModelConfigService(tenant_id=1)

        result = service._merge_model_params(None, {"temperature": 0.7})

        assert result == {"temperature": 0.7}


class TestUpdateAgentModelParams:
    """Tests for persisting model params during agent config updates."""

    @pytest.mark.asyncio
    async def test_update_agent_model_persists_params(self):
        cipher = FieldCipher()
        encrypted_key = cipher.encrypt("test-api-key")
        tenant = MagicMock()
        tenant.config = {
            "llm_config": {
                "agent_model": {
                    "name": "Old Model",
                    "type": "openai-compatible",
                    "api_base": "https://example.com/v1",
                    "api_key": encrypted_key,
                    "model_id": "old-model",
                    "params": {"temperature": 0.1, "max_tokens": 4000},
                }
            }
        }

        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=tenant)
        mock_repo.db = MagicMock()
        mock_repo.db.commit = AsyncMock()

        service = TenantModelConfigService(tenant_id=1, db=mock_repo.db)
        service._tenant_repo = mock_repo

        config = ModelConfigDTO(
            name="New Model",
            type="openai-compatible",
            api_base="https://example.com/v1",
            api_key="",
            model_id="new-model",
            params={"temperature": 0.5, "max_tokens": 8000},
        )

        await service.update_agent_model(config)

        saved = tenant.config["llm_config"]["agent_model"]
        assert saved["model_id"] == "new-model"
        assert saved["params"] == {"temperature": 0.5, "max_tokens": 8000}
        assert saved["api_key"] == encrypted_key

    @pytest.mark.asyncio
    async def test_update_agent_model_preserves_params_when_not_provided(self):
        cipher = FieldCipher()
        encrypted_key = cipher.encrypt("test-api-key")
        tenant = MagicMock()
        tenant.config = {
            "llm_config": {
                "agent_model": {
                    "name": "Model",
                    "type": "openai-compatible",
                    "api_base": "https://example.com/v1",
                    "api_key": encrypted_key,
                    "model_id": "model-a",
                    "params": {"temperature": 0.3, "max_tokens": 6000, "top_p": 0.8},
                }
            }
        }

        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=tenant)
        mock_repo.db = MagicMock()
        mock_repo.db.commit = AsyncMock()

        service = TenantModelConfigService(tenant_id=1, db=mock_repo.db)
        service._tenant_repo = mock_repo

        config = ModelConfigDTO(
            name="Model",
            type="openai-compatible",
            api_base="https://example.com/v1",
            api_key="",
            model_id="model-b",
            params=None,
        )

        await service.update_agent_model(config)

        saved = tenant.config["llm_config"]["agent_model"]
        assert saved["model_id"] == "model-b"
        assert saved["params"] == {"temperature": 0.3, "max_tokens": 6000, "top_p": 0.8}


class TestResolveStoredApiKey:
    """Tests for resolving stored API keys during connection tests."""

    @pytest.mark.asyncio
    async def test_resolve_stored_api_key_from_agent_model(self):
        cipher = FieldCipher()
        encrypted_key = cipher.encrypt("stored-key")
        tenant = MagicMock()
        tenant.config = {
            "llm_config": {
                "agent_model": {
                    "api_key": encrypted_key,
                }
            }
        }

        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=tenant)

        service = TenantModelConfigService(tenant_id=1, db=MagicMock())
        service._tenant_repo = mock_repo

        resolved = await service._resolve_stored_api_key("agent_model")

        assert resolved == "stored-key"


class TestClearVectorCollection:
    """Tests for _clear_vector_collection method."""

    @pytest.mark.asyncio
    async def test_clear_vector_collection_calls_rag_manager(self):
        """Should call RAGManager.clear_collection()."""
        service = TenantModelConfigService(tenant_id=1)

        mock_rag_manager = MagicMock()
        mock_rag_manager.clear_collection = AsyncMock()

        with patch(
            "apps.shared.infra.rag.rag_manager.RAGManager",
            return_value=mock_rag_manager,
        ):
            await service._clear_vector_collection()

        mock_rag_manager.clear_collection.assert_called_once()

    @pytest.mark.asyncio
    async def test_clear_vector_collection_handles_exception_gracefully(self):
        """Should not raise exception if collection deletion fails."""
        service = TenantModelConfigService(tenant_id=1)

        mock_rag_manager = MagicMock()
        mock_rag_manager.clear_collection = AsyncMock(side_effect=Exception("Connection failed"))

        with patch(
            "apps.shared.infra.rag.rag_manager.RAGManager",
            return_value=mock_rag_manager,
        ):
            # Should not raise
            await service._clear_vector_collection()
