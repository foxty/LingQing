"""Tenant model config service - handles tenant-scoped LLM and Embedding model configuration.

This service manages tenant-level LLM and Embedding configurations with encrypted API keys.
Service layer handles DTO ↔ encrypted dict conversion.
"""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from apps.shared.core.exceptions import ResourceNotFoundError, ValidationError
from apps.shared.infra.llm.llm_model_factory import LLMModelFactory
from apps.shared.schemas.model_config import (
    EmbeddingModelConfigResponseDTO,
    ModelConfigDTO,
    ModelConfigResponseDTO,
    TenantEmbeddingConfigDTO,
    TenantEmbeddingConfigResponseDTO,
    TenantLLMConfigDTO,
    TenantLLMConfigResponseDTO,
)
from apps.shared.utils.field_cipher import FieldCipher
from apps.shared.utils.logger import get_logger
from apps.tenant_app_service.tenant.repository import TenantRepository

logger = get_logger(__name__)


class TenantModelConfigService:
    """Service for managing tenant-scoped LLM and Embedding configuration.

    This service:
    1. Encrypts API keys before storage
    2. Masks API keys for API responses
    3. Orchestrates tenant repository operations for model config
    """

    def __init__(self, tenant_id: int, db: AsyncSession | None = None):
        """Initialize service.

        Args:
            tenant_id: Tenant ID
            db: Database session (optional - only needed for get/update operations)
        """
        self.tenant_id = tenant_id
        self._cipher = FieldCipher()
        self._tenant_repo = TenantRepository(db) if db else None

    # ==================== LLM Config Methods ====================

    async def get_llm_config(self) -> TenantLLMConfigResponseDTO:
        """Get tenant's current LLM configuration.

        Returns:
            TenantLLMConfigResponseDTO with masked API keys

        Raises:
            ResourceNotFoundError: If tenant not found
            ValidationError: If LLM config not configured
        """
        if not self._tenant_repo:
            raise RuntimeError("Database session required for get_llm_config")

        tenant = await self._tenant_repo.get_by_id(self.tenant_id)
        if not tenant:
            raise ResourceNotFoundError(f"Tenant {self.tenant_id} not found")

        response = self._prepare_llm_for_response(tenant.config)
        if not response:
            raise ValidationError("LLM config not configured for this tenant")
        return response

    async def update_llm_config(self, config: TenantLLMConfigDTO) -> TenantLLMConfigResponseDTO:
        """Update tenant's LLM configuration.

        Validates, encrypts API keys, and saves to database.

        Args:
            config: New LLM configuration with plain API keys

        Returns:
            TenantLLMConfigResponseDTO with masked API keys

        Raises:
            ResourceNotFoundError: If tenant not found
            ValidationError: If config validation fails
        """
        if not self._tenant_repo:
            raise RuntimeError("Database session required for update_llm_config")

        logger.info(f"Updating LLM config for tenant {self.tenant_id}")

        # Validate config
        self._validate_llm_config(config)

        # Prepare for storage (encrypt API keys)
        config_dict = self._prepare_llm_for_storage(config)

        # Get current tenant config and merge
        tenant = await self._tenant_repo.get_by_id(self.tenant_id)
        if not tenant:
            raise ResourceNotFoundError(f"Tenant {self.tenant_id} not found")

        existing_config = tenant.config or {}
        updated_config = {**existing_config, **config_dict}

        # Save to database
        await self._tenant_repo.update_tenant(self.tenant_id, config=updated_config)

        logger.info(f"Tenant {self.tenant_id} LLM config updated successfully")

        # Return with masked keys
        return self._prepare_llm_for_response(updated_config)

    def _prepare_llm_for_storage(self, config: TenantLLMConfigDTO) -> dict:
        """Prepare LLM config for database storage (encrypt API keys)."""
        agent_model_dict = config.agent_model.model_dump()
        mini_agent_model_dict = config.mini_agent_model.model_dump()

        # Encrypt API keys
        agent_model_dict["api_key"] = self._cipher.encrypt(agent_model_dict["api_key"])
        mini_agent_model_dict["api_key"] = self._cipher.encrypt(mini_agent_model_dict["api_key"])

        return {
            "llm_config": {
                "agent_model": agent_model_dict,
                "mini_agent_model": mini_agent_model_dict,
            }
        }

    def _prepare_llm_for_response(self, tenant_config: dict | None) -> TenantLLMConfigResponseDTO | None:
        """Prepare tenant config for API response (mask API keys)."""
        if not tenant_config:
            return None

        llm_config = tenant_config.get("llm_config")
        if not llm_config:
            return None

        agent_model_data = llm_config.get("agent_model")
        mini_agent_model_data = llm_config.get("mini_agent_model")

        # Build agent model response (or empty placeholder)
        if agent_model_data:
            agent_api_key = self._cipher.decrypt(agent_model_data.get("api_key", ""))
            agent_model_resp = ModelConfigResponseDTO(
                name=agent_model_data.get("name", ""),
                type=agent_model_data.get("type", "openai-compatible"),
                api_base=agent_model_data.get("api_base", ""),
                api_key_masked=FieldCipher.mask_value(agent_api_key),
                model_id=agent_model_data.get("model_id", ""),
                params=agent_model_data.get("params"),
            )
        else:
            agent_model_resp = ModelConfigResponseDTO(
                name="", type="openai-compatible", api_base="", api_key_masked="", model_id=""
            )

        # Build mini agent model response (or empty placeholder)
        if mini_agent_model_data:
            mini_api_key = self._cipher.decrypt(mini_agent_model_data.get("api_key", ""))
            mini_agent_model_resp = ModelConfigResponseDTO(
                name=mini_agent_model_data.get("name", ""),
                type=mini_agent_model_data.get("type", "openai-compatible"),
                api_base=mini_agent_model_data.get("api_base", ""),
                api_key_masked=FieldCipher.mask_value(mini_api_key),
                model_id=mini_agent_model_data.get("model_id", ""),
                params=mini_agent_model_data.get("params"),
            )
        else:
            mini_agent_model_resp = ModelConfigResponseDTO(
                name="", type="openai-compatible", api_base="", api_key_masked="", model_id=""
            )

        return TenantLLMConfigResponseDTO(
            agent_model=agent_model_resp,
            mini_agent_model=mini_agent_model_resp,
        )

    def _validate_llm_config(self, config: TenantLLMConfigDTO) -> None:
        """Validate LLM config."""
        if not config.agent_model.api_key:
            raise ValueError("agent_model.api_key is required")
        if not config.agent_model.api_base:
            raise ValueError("agent_model.api_base is required")
        if not config.agent_model.model_id:
            raise ValueError("agent_model.model_id is required")
        if not config.mini_agent_model.api_key:
            raise ValueError("mini_agent_model.api_key is required")
        if not config.mini_agent_model.api_base:
            raise ValueError("mini_agent_model.api_base is required")
        if not config.mini_agent_model.model_id:
            raise ValueError("mini_agent_model.model_id is required")

        logger.info(f"LLM config validated for tenant {self.tenant_id}")

    async def _resolve_stored_api_key(self, config_key: str) -> str:
        """Resolve API key from stored tenant LLM config when not provided in request."""
        if not self._tenant_repo:
            raise RuntimeError("Database session required to resolve stored API key")

        tenant = await self._tenant_repo.get_by_id(self.tenant_id)
        if not tenant:
            raise ResourceNotFoundError(f"Tenant {self.tenant_id} not found")

        llm_config = (tenant.config or {}).get("llm_config", {})
        stored_key = (llm_config.get(config_key) or {}).get("api_key")
        if not stored_key:
            return ""

        return self._cipher.decrypt(stored_key)

    async def _resolve_stored_embedding_api_key(self) -> str:
        """Resolve API key from stored tenant embedding config when not provided in request."""
        if not self._tenant_repo:
            raise RuntimeError("Database session required to resolve stored API key")

        tenant = await self._tenant_repo.get_by_id(self.tenant_id)
        if not tenant:
            raise ResourceNotFoundError(f"Tenant {self.tenant_id} not found")

        embedding_model = ((tenant.config or {}).get("embedding_config") or {}).get("embedding_model") or {}
        stored_key = embedding_model.get("api_key")
        if not stored_key:
            return ""

        return self._cipher.decrypt(stored_key)

    async def test_llm_connection(self, api_base: str, model_id: str, api_key: str) -> str:
        """Test LLM connection by making an actual API call.

        Args:
            api_base: API base URL
            model_id: Model ID
            api_key: API key

        Returns:
            Success message

        Raises:
            ValueError: If parameters are invalid or connection fails
        """
        if not api_key:
            api_key = await self._resolve_stored_api_key("agent_model")
        if not api_key:
            raise ValueError("API key is required")
        if not api_base:
            raise ValueError("API base URL is required")
        if not model_id:
            raise ValueError("Model ID is required")

        # Build minimal config for factory
        encrypted_key = self._cipher.encrypt(api_key)
        config_dict = {
            "llm_config": {
                "agent_model": {
                    "name": "test",
                    "type": "openai-compatible",
                    "api_base": api_base,
                    "api_key": encrypted_key,
                    "model_id": model_id,
                }
            }
        }

        try:
            factory = LLMModelFactory(config_dict)
            llm = factory.get_agent_model()
            await llm.ainvoke("Hello, this is a connection test. Please respond with 'OK'.")
        except Exception as e:
            logger.error(f"Connection test failed: {e}", exc_info=True)
            raise ValidationError(f"Connection test failed: {e}")

        return "Connection test passed"

    async def update_agent_model(self, config: ModelConfigDTO) -> TenantLLMConfigResponseDTO:
        """Update only the agent model configuration."""
        if not self._tenant_repo:
            raise RuntimeError("Database session required for update_agent_model")

        logger.info(f"Updating agent model config for tenant {self.tenant_id}")

        tenant = await self._tenant_repo.get_by_id(self.tenant_id)
        if not tenant:
            raise ResourceNotFoundError(f"Tenant {self.tenant_id} not found")

        existing_config = tenant.config or {}
        llm_config = existing_config.get("llm_config", {})
        existing_agent = llm_config.get("agent_model", {})

        allow_empty_key = bool(existing_agent.get("api_key")) and not config.api_key
        self._validate_single_config(config, "agent_model", allow_empty_key)

        agent_dict = config.model_dump()
        if config.api_key:
            agent_dict["api_key"] = self._cipher.encrypt(agent_dict["api_key"])
        elif existing_agent.get("api_key"):
            agent_dict["api_key"] = existing_agent["api_key"]

        agent_dict["params"] = self._merge_model_params(existing_agent.get("params"), config.params)

        llm_config["agent_model"] = agent_dict

        tenant.config = {**existing_config, "llm_config": llm_config}
        flag_modified(tenant, "config")
        await self._tenant_repo.db.commit()

        return self._prepare_llm_for_response(tenant.config)

    async def copy_agent_to_mini(self) -> TenantLLMConfigResponseDTO:
        """Copy agent model config to mini agent model."""
        if not self._tenant_repo:
            raise RuntimeError("Database session required for copy_agent_to_mini")

        logger.info(f"Copying agent model config to mini agent for tenant {self.tenant_id}")

        tenant = await self._tenant_repo.get_by_id(self.tenant_id)
        if not tenant:
            raise ResourceNotFoundError(f"Tenant {self.tenant_id} not found")

        existing_config = tenant.config or {}
        llm_config = existing_config.get("llm_config", {})
        existing_agent = llm_config.get("agent_model")

        if not existing_agent:
            raise ValidationError("Agent model not configured. Please configure agent first.")

        llm_config["mini_agent_model"] = {**existing_agent}

        tenant.config = {**existing_config, "llm_config": llm_config}
        flag_modified(tenant, "config")
        await self._tenant_repo.db.commit()

        logger.info(f"Agent model config copied to mini agent for tenant {self.tenant_id}")

        return self._prepare_llm_for_response(tenant.config)

    async def update_mini_agent_model(self, config: ModelConfigDTO) -> TenantLLMConfigResponseDTO:
        """Update only the mini agent model configuration."""
        if not self._tenant_repo:
            raise RuntimeError("Database session required for update_mini_agent_model")

        logger.info(f"Updating mini agent model config for tenant {self.tenant_id}")

        tenant = await self._tenant_repo.get_by_id(self.tenant_id)
        if not tenant:
            raise ResourceNotFoundError(f"Tenant {self.tenant_id} not found")

        existing_config = tenant.config or {}
        llm_config = existing_config.get("llm_config", {})
        existing_mini = llm_config.get("mini_agent_model", {})
        existing_agent = llm_config.get("agent_model", {})

        allow_empty_key = (
            bool(existing_mini.get("api_key")) or bool(existing_agent.get("api_key"))
        ) and not config.api_key
        self._validate_single_config(config, "mini_agent_model", allow_empty_key)

        mini_dict = config.model_dump()
        if config.api_key:
            mini_dict["api_key"] = self._cipher.encrypt(mini_dict["api_key"])
        elif existing_mini.get("api_key"):
            mini_dict["api_key"] = existing_mini["api_key"]
        elif existing_agent.get("api_key"):
            mini_dict["api_key"] = existing_agent["api_key"]

        mini_dict["params"] = self._merge_model_params(existing_mini.get("params"), config.params)

        llm_config["mini_agent_model"] = mini_dict

        tenant.config = {**existing_config, "llm_config": llm_config}
        flag_modified(tenant, "config")
        await self._tenant_repo.db.commit()

        return self._prepare_llm_for_response(tenant.config)

    def _merge_model_params(
        self,
        existing_params: dict | None,
        incoming_params: dict | None,
    ) -> dict | None:
        """Merge incoming model params with existing stored params."""
        if incoming_params is None:
            return existing_params or None

        merged = dict(existing_params or {})
        merged.update(incoming_params)
        return merged

    def _validate_single_config(self, config: ModelConfigDTO, prefix: str, allow_empty_key: bool = False) -> None:
        """Validate a single model config (agent or mini_agent)."""
        if not allow_empty_key and not config.api_key:
            raise ValueError(f"{prefix}.api_key is required")
        if not config.api_base:
            raise ValueError(f"{prefix}.api_base is required")
        if not config.model_id:
            raise ValueError(f"{prefix}.model_id is required")

    # ==================== Embedding Config Methods ====================

    async def get_embedding_config(self) -> TenantEmbeddingConfigResponseDTO | None:
        """Get tenant's current Embedding configuration.

        Returns:
            TenantEmbeddingConfigResponseDTO with masked API keys, or None if not configured.
        """
        if not self._tenant_repo:
            raise RuntimeError("Database session required for get_embedding_config")

        tenant = await self._tenant_repo.get_by_id(self.tenant_id)
        if not tenant:
            raise ResourceNotFoundError(f"Tenant {self.tenant_id} not found")

        response = self._prepare_embedding_for_response(tenant.config)
        return response

    async def update_embedding_config(self, config: TenantEmbeddingConfigDTO) -> TenantEmbeddingConfigResponseDTO:
        """Update tenant's Embedding configuration.

        Validates, encrypts API keys, and saves to database.
        If api_key is empty and an existing key is configured, keeps the existing key.

        Args:
            config: New Embedding configuration with plain API keys

        Returns:
            TenantEmbeddingConfigResponseDTO with masked API keys

        Raises:
            ResourceNotFoundError: If tenant not found
            ValidationError: If config validation fails
        """
        if not self._tenant_repo:
            raise RuntimeError("Database session required for update_embedding_config")

        logger.info(f"Updating Embedding config for tenant {self.tenant_id}")

        # Get current tenant config first to check existing key
        tenant = await self._tenant_repo.get_by_id(self.tenant_id)
        if not tenant:
            raise ResourceNotFoundError(f"Tenant {self.tenant_id} not found")

        existing_config = tenant.config or {}
        existing_embedding = (existing_config.get("embedding_config") or {}).get("embedding_model", {})

        # Validate config (allow empty api_key if existing key is present)
        allow_empty_key = bool(existing_embedding.get("api_key")) and not config.embedding_model.api_key
        self._validate_embedding_config(config, allow_empty_key)

        # Prepare for storage (encrypt API keys, keep existing if not provided)
        config_dict = self._prepare_embedding_for_storage(config, existing_embedding)

        updated_config = {**existing_config, **config_dict}

        # Save to database
        await self._tenant_repo.update_tenant(self.tenant_id, config=updated_config)

        logger.info(f"Tenant {self.tenant_id} Embedding config updated successfully")

        # Check if embedding model changed (model_id or api_base)
        model_changed = self._embedding_model_changed(existing_embedding, config_dict)

        if model_changed:
            # Delete the entire vector collection to avoid dimension mismatch
            await self._clear_vector_collection()
            # Mark all resource index records as stale to trigger re-indexing
            await self._mark_resource_index_stale()

        # Return with masked keys
        return self._prepare_embedding_for_response(updated_config)

    def _embedding_model_changed(self, existing_embedding: dict, new_config_dict: dict) -> bool:
        """Check if the embedding model configuration actually changed.

        Args:
            existing_embedding: Current embedding model config from DB
            new_config_dict: New embedding config dict (prepared for storage)

        Returns:
            True if model_id or api_base changed, False otherwise
        """
        if not existing_embedding:
            # No existing config, so this is a new setup
            return True

        new_embedding = new_config_dict.get("embedding_config", {}).get("embedding_model", {})

        existing_model_id = existing_embedding.get("model_id", "")
        new_model_id = new_embedding.get("model_id", "")

        existing_api_base = existing_embedding.get("api_base", "")
        new_api_base = new_embedding.get("api_base", "")

        changed = existing_model_id != new_model_id or existing_api_base != new_api_base

        if changed:
            logger.info(
                "Embedding model changed for tenant %d: model_id %s -> %s, api_base %s -> %s",
                self.tenant_id,
                existing_model_id,
                new_model_id,
                existing_api_base,
                new_api_base,
            )

        return changed

    async def _clear_vector_collection(self) -> None:
        """Delete the entire vector collection for this tenant.

        Called when embedding model changes to avoid dimension mismatch.
        The collection will be recreated on next indexing with the new embedding model.
        """
        try:
            from apps.shared.infra.rag.rag_manager import RAGManager

            rag_manager = RAGManager(tenant_id=self.tenant_id)
            await rag_manager.clear_collection()
            logger.info(
                "Vector collection cleared for tenant %d due to embedding model change",
                self.tenant_id,
            )
        except Exception as exc:
            logger.error(
                "Failed to clear vector collection for tenant %d: %s",
                self.tenant_id,
                exc,
            )
            # Don't fail the embedding config update if collection deletion fails
            # The stale marking will still trigger re-indexing

    def _prepare_embedding_for_storage(self, config: TenantEmbeddingConfigDTO, existing_embedding: dict = None) -> dict:
        """Prepare Embedding config for database storage (encrypt API keys)."""
        embedding_model_dict = config.embedding_model.model_dump()

        # Encrypt API key, or keep existing if not provided
        if config.embedding_model.api_key:
            embedding_model_dict["api_key"] = self._cipher.encrypt(embedding_model_dict["api_key"])
        elif existing_embedding and existing_embedding.get("api_key"):
            embedding_model_dict["api_key"] = existing_embedding["api_key"]

        return {
            "embedding_config": {
                "embedding_model": embedding_model_dict,
            }
        }

    def _prepare_embedding_for_response(self, tenant_config: dict | None) -> TenantEmbeddingConfigResponseDTO | None:
        """Prepare tenant config for API response (mask API keys)."""
        if not tenant_config:
            return None

        embedding_config = tenant_config.get("embedding_config")
        if not embedding_config:
            return None

        embedding_model_data = embedding_config.get("embedding_model")

        if embedding_model_data:
            embedding_api_key = self._cipher.decrypt(embedding_model_data.get("api_key", ""))
            embedding_model_resp = EmbeddingModelConfigResponseDTO(
                name=embedding_model_data.get("name", ""),
                type=embedding_model_data.get("type", "openai-compatible"),
                api_base=embedding_model_data.get("api_base", ""),
                api_key_masked=FieldCipher.mask_value(embedding_api_key),
                model_id=embedding_model_data.get("model_id", ""),
            )
        else:
            embedding_model_resp = EmbeddingModelConfigResponseDTO(
                name="", type="openai-compatible", api_base="", api_key_masked="", model_id=""
            )

        return TenantEmbeddingConfigResponseDTO(embedding_model=embedding_model_resp)

    def _validate_embedding_config(self, config: TenantEmbeddingConfigDTO, allow_empty_key: bool = False) -> None:
        """Validate Embedding config."""
        if not allow_empty_key and not config.embedding_model.api_key:
            raise ValueError("embedding_model.api_key is required")
        if not config.embedding_model.api_base:
            raise ValueError("embedding_model.api_base is required")
        if not config.embedding_model.model_id:
            raise ValueError("embedding_model.model_id is required")

        logger.info(f"Embedding config validated for tenant {self.tenant_id}")

    async def test_embedding_connection(self, api_base: str, model_id: str, api_key: str) -> str:
        """Test Embedding connection by making an actual API call.

        Args:
            api_base: API base URL
            model_id: Model ID
            api_key: API key

        Returns:
            Success message

        Raises:
            ValueError: If parameters are invalid or connection fails
        """
        if not api_key:
            api_key = await self._resolve_stored_embedding_api_key()
        if not api_key:
            raise ValueError("API key is required")
        if not api_base:
            raise ValueError("API base URL is required")
        if not model_id:
            raise ValueError("Model ID is required")

        # Build minimal config for factory
        encrypted_key = self._cipher.encrypt(api_key)
        config_dict = {
            "embedding_config": {
                "embedding_model": {
                    "name": "test",
                    "type": "openai-compatible",
                    "api_base": api_base,
                    "api_key": encrypted_key,
                    "model_id": model_id,
                }
            }
        }

        try:
            from apps.shared.infra.rag.embedding_utils import create_embeddings_from_config

            embeddings = create_embeddings_from_config(config_dict)
            # Make an actual embedding call to validate the connection
            await embeddings.aembed_query("Hello, this is a connection test.")
        except Exception as e:
            raise ValueError(f"Connection test failed: {e}")

        return "Connection test passed"

    async def _mark_resource_index_stale(self) -> None:
        """Mark all resource index records as stale when embedding model changes.

        This triggers the scheduler to re-index all resources with the new embedding model.
        """
        try:
            from apps.shared.search.indexing_service import ResourceIndexService

            resource_index_svc = ResourceIndexService(tenant_id=self.tenant_id, db_session=self._tenant_repo.db)
            count = await resource_index_svc.mark_all_vectors_stale()
            logger.info(
                "Marked %d resource index records as stale for embedding model change (tenant %d)",
                count,
                self.tenant_id,
            )
        except Exception as exc:
            logger.error(
                "Failed to mark resource index as stale for tenant %d: %s",
                self.tenant_id,
                exc,
            )
            # Don't fail the embedding config update if stale marking fails
