"""LLM model factory - creates LangChain model instances from config.

Infrastructure layer - no dependency on application/business logic.
Accepts encrypted config dict, handles decryption internally, returns typed DTOs.
"""

from typing import Any

from langchain_core.language_models import BaseChatModel

from apps.shared.schemas.model_config import ModelConfigDTO
from apps.shared.utils.field_cipher import FieldCipher
from apps.shared.utils.logger import get_logger

logger = get_logger(__name__)


class LLMModelFactory:
    """Factory for creating LangChain model instances from encrypted config.

    This factory accepts encrypted config dict, handles decryption internally,
    and works with typed ModelConfigDTO objects.
    Infrastructure layer component - used by AgentBase and MiniAgentExecutor.
    """

    def __init__(self, encrypted_config: dict | None):
        """Initialize with encrypted config dict.

        Args:
            encrypted_config: Encrypted tenant.config dict (contains llm_config with encrypted API keys)
        """
        self._cipher = FieldCipher()
        self._agent_model: ModelConfigDTO | None = None
        self._mini_agent_model: ModelConfigDTO | None = None

        if encrypted_config:
            llm_config = encrypted_config.get("llm_config")
            if llm_config:
                self._agent_model = self._decrypt_model(llm_config.get("agent_model"))
                self._mini_agent_model = self._decrypt_model(llm_config.get("mini_agent_model"))

    def _decrypt_model(self, model_data: dict | None) -> ModelConfigDTO | None:
        """Decrypt model config and return typed DTO."""
        if not model_data:
            return None
        decrypted = model_data.copy()
        api_key = decrypted.get("api_key", "")
        if api_key:
            decrypted["api_key"] = self._cipher.decrypt(api_key)
        return ModelConfigDTO(**decrypted)

    def is_configured(self) -> bool:
        """Check if LLM config is configured."""
        return self._agent_model is not None or self._mini_agent_model is not None

    def get_agent_model(self) -> BaseChatModel:
        """Get LangChain model instance for main agent."""
        if not self._agent_model:
            raise ValueError("LLM config not configured. Please configure agent_model.")
        return self._create_model(self._agent_model)

    def get_mini_agent_model(self) -> BaseChatModel:
        """Get LangChain model instance for mini agent."""
        if not self._mini_agent_model:
            raise ValueError("LLM config not configured. Please configure mini_agent_model.")
        return self._create_model(self._mini_agent_model)

    def get_model_name(self, model_type: str = "agent_model") -> str:
        """Get display name for a model type (for metrics)."""
        model = self._agent_model if model_type == "agent_model" else self._mini_agent_model
        if not model:
            return ""
        return model.name

    def get_agent_model_id(self) -> str | None:
        """Get configured model_id for the main agent."""
        return self._agent_model.model_id if self._agent_model else None

    def get_mini_agent_model_id(self) -> str | None:
        """Get configured model_id for the mini agent."""
        return self._mini_agent_model.model_id if self._mini_agent_model else None

    def get_agent_max_output_tokens(self) -> int | None:
        """Get configured max output tokens for the main agent model."""
        if not self._agent_model or not self._agent_model.params:
            return None
        max_tokens = self._agent_model.params.get("max_tokens")
        return int(max_tokens) if max_tokens is not None else None

    def _create_model(self, config: ModelConfigDTO) -> BaseChatModel:
        """Create LangChain model instance from typed DTO.

        Args:
            config: Decrypted ModelConfigDTO

        Returns:
            BaseChatModel instance
        """
        if not config.api_key:
            raise ValueError(f"API key not set for model '{config.name}'.")
        if not config.api_base:
            raise ValueError(f"API base not set for model '{config.name}'.")

        params = config.params or {}
        temperature = params.get("temperature", 0.1)
        max_tokens = params.get("max_tokens")
        top_p = params.get("top_p")

        logger.info(
            f"Creating model: {config.name} (type={config.type}, model_id={config.model_id}, max_tokens={max_tokens}, temperature={temperature})"
        )

        return self._create_model_instance(
            model_id=config.model_id,
            api_base=config.api_base,
            api_key=config.api_key,
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
        )

    def _create_model_instance(
        self,
        model_id: str,
        api_base: str,
        api_key: str,
        temperature: float,
        top_p: float | None,
        max_tokens: int | None,
    ) -> BaseChatModel:
        """Create an OpenAI-compatible LangChain chat model."""
        from langchain_openai import ChatOpenAI

        kwargs: dict[str, Any] = {
            "model": model_id,
            "temperature": temperature,
            "api_key": api_key,
            "base_url": api_base,
            "stream_usage": False,
        }
        if not _is_databricks_ai_gateway(api_base):
            kwargs["extra_body"] = {"thinking": {"type": "disabled"}}
        if top_p is not None:
            kwargs["top_p"] = top_p
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens

        return ChatOpenAI(**kwargs)


def _is_databricks_ai_gateway(api_base: str) -> bool:
    """Return True when api_base points at Databricks AI Gateway."""
    normalized = api_base.lower()
    return "databricks.com" in normalized or "/ai-gateway/" in normalized
