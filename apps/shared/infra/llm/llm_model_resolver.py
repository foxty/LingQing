"""Create LangChain model instances from resolved tenant registry config."""

from __future__ import annotations

from typing import Any

from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseChatModel

from apps.shared.llm_providers.domain import ResolvedModelConfig
from apps.shared.utils.logger import get_logger

logger = get_logger(__name__)

_DATABRICKS_AI_GATEWAY_PRESET = "databricks-ai-gateway"


def create_chat_model(resolved: ResolvedModelConfig) -> BaseChatModel:
    """Create a ChatOpenAI instance from a resolved registry profile."""
    params = resolved.params or {}
    temperature = params.get("temperature", 0.1)
    max_tokens = params.get("max_tokens")
    top_p = params.get("top_p")

    logger.info(
        "Creating chat model profile=%s model_id=%s provider=%s",
        resolved.profile_name,
        resolved.model_id,
        resolved.provider_display_name,
    )
    return _create_openai_compatible_chat_model(
        resolved=resolved,
        model_id=resolved.model_id,
        api_base=resolved.api_base,
        api_key=resolved.api_key,
        temperature=temperature,
        top_p=top_p,
        max_tokens=max_tokens,
    )


def create_embeddings(resolved: ResolvedModelConfig) -> Embeddings:
    """Create OpenAIEmbeddings from a resolved embedding profile."""
    from langchain_openai import OpenAIEmbeddings

    logger.info(
        "Creating embedding model profile=%s model_id=%s provider=%s",
        resolved.profile_name,
        resolved.model_id,
        resolved.provider_display_name,
    )
    return OpenAIEmbeddings(
        model=resolved.model_id,
        api_key=resolved.api_key,
        base_url=resolved.api_base,
        check_embedding_ctx_length=False,
    )


def _create_openai_compatible_chat_model(
    *,
    resolved: ResolvedModelConfig,
    model_id: str,
    api_base: str,
    api_key: str,
    temperature: float,
    top_p: float | None,
    max_tokens: int | None,
) -> BaseChatModel:
    from langchain_openai import ChatOpenAI

    kwargs: dict[str, Any] = {
        "model": model_id,
        "temperature": temperature,
        "api_key": api_key,
        "base_url": api_base,
        "stream_usage": False,
    }
    if resolved.provider_preset_key != _DATABRICKS_AI_GATEWAY_PRESET:
        kwargs["extra_body"] = {"thinking": {"type": "disabled"}}
    if top_p is not None:
        kwargs["top_p"] = top_p
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens
    return ChatOpenAI(**kwargs)
