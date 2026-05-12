import warnings

from apps.shared.schemas.model_config import (  # noqa: E402, F401
    EmbeddingModelConfigDTO,
    EmbeddingModelConfigResponseDTO,
    ModelCategory,
    ModelConfigDTO,
    ModelConfigResponseDTO,
    ModelDTO,
    ModelParamsDTO,
    ProviderDTO,
    ProviderWithModelsByCategoryDTO,
    ProviderWithModelsDTO,
    TenantEmbeddingConfigDTO,
    TenantEmbeddingConfigResponseDTO,
    TenantLLMConfigDTO,
    TenantLLMConfigResponseDTO,
)

warnings.warn(
    "apps.shared.infra.llm.schemas is deprecated. "
    "Use apps.shared.schemas.model_config instead.",
    DeprecationWarning,
    stacklevel=2,
)
