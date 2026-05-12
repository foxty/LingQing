"""Embedding utilities for RAG system.

Provides shared functions for creating embeddings from tenant config.
"""

from langchain_core.embeddings import Embeddings
from pydantic import ValidationError

from apps.shared.schemas.model_config import TenantEmbeddingConfigDTO
from apps.shared.utils.logger import get_logger

logger = get_logger(__name__)


def create_embeddings_from_config(tenant_config: dict | None) -> Embeddings | None:
    """Create embeddings instance from tenant config dict.

    Uses Pydantic DTO for structure validation, then creates the embedding instance.

    Args:
        tenant_config: Tenant config dict (raw from DB or service layer).

    Returns:
        OpenAIEmbeddings instance or None if config is missing/invalid.
    """
    if not tenant_config:
        logger.info("Embedding: no tenant config provided, using default embedding")
        return None

    raw_embedding_config = tenant_config.get("embedding_config")
    if not raw_embedding_config:
        logger.info("Embedding: no embedding_config in tenant config, using default embedding")
        return None

    # Validate structure with Pydantic DTO
    try:
        embedding_cfg = TenantEmbeddingConfigDTO.model_validate(raw_embedding_config)
    except ValidationError as e:
        logger.warning("Embedding: invalid config structure, using default embedding: %s", e)
        return None

    from apps.shared.utils.field_cipher import FieldCipher

    cipher = FieldCipher()
    model_data = embedding_cfg.embedding_model
    encrypted_api_key = model_data.api_key
    try:
        api_key = cipher.decrypt(encrypted_api_key)
    except Exception:
        api_key = encrypted_api_key

    api_base = model_data.api_base
    model_id = model_data.model_id
    model_name = model_data.name

    logger.info(
        "Embedding: using tenant-configured model '%s' (id=%s, api_base=%s)",
        model_name,
        model_id,
        api_base,
    )

    # Use OpenAIEmbeddings with check_embedding_ctx_length=False to use simple API path
    # This avoids input format issues with certain providers like DashScope compatible mode
    from langchain_openai import OpenAIEmbeddings

    return OpenAIEmbeddings(
        openai_api_key=api_key,
        openai_api_base=api_base,
        model=model_id,
        check_embedding_ctx_length=False,
    )
