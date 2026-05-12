"""Model registry - loads and provides system preset provider/model information from YAML config.

This module handles:
1. Loading model configuration from models.yaml
2. Providing provider/model metadata for UI display
3. Supporting LLM and Embedding model categories
4. No longer responsible for model instance creation (moved to LLMModelFactory)
"""

from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

from apps.shared.infra.llm.model_profile import ModelProfile
from apps.shared.schemas.model_config import ModelCategory
from apps.shared.utils.logger import get_logger

logger = get_logger(__name__)


class ModelRegistry:
    """LLM model registry for system preset providers/models.

    Responsibilities:
    1. Load model configuration from YAML file
    2. Provide provider/model metadata for UI display
    3. No longer creates model instances (moved to LLMModelFactory)
    """

    def __init__(self, config_path: str | None = None):
        """Initialize model registry.

        Args:
            config_path: Path to models.yaml, defaults to apps/shared/infra/llm/models.yaml
        """
        if config_path is None:
            config_path = Path(__file__).parent / "models.yaml"

        self.config_path = Path(config_path)
        self._profiles: dict[str, ModelProfile] = {}
        self._embedding_profiles: dict[str, ModelProfile] = {}
        self._load_config()

    def _load_config(self):
        """Load model configuration from YAML file."""
        if not self.config_path.exists():
            logger.warning(f"Model config file not found: {self.config_path}")
            return

        try:
            with open(self.config_path) as f:
                config = yaml.safe_load(f)

            global_default_params = config.get("default_params", {}) or {}
            providers = config.get("providers", []) or []
            if not providers:
                raise ValueError("Invalid models.yaml: 'providers' is required and must be non-empty")

            for provider_data in providers:
                provider_name = provider_data.get("provider")
                if not provider_name:
                    raise ValueError("Invalid provider config: 'provider' is required")

                provider_api_base = provider_data.get("api_base")
                provider_api_base_env = provider_data.get("api_base_env")
                provider_embedding_api_base = provider_data.get("embedding_api_base")
                provider_default_params = provider_data.get("default_params", {}) or {}
                inherited_defaults = {**global_default_params, **provider_default_params}

                # Load LLM models
                for model_entry in provider_data.get("llm_models", []) or []:
                    if isinstance(model_entry, str):
                        model_id = model_entry
                        key = f"{provider_name}-{model_id}"
                        model_data = {
                            "key": key,
                            "name": model_id,
                            "model_id": model_id,
                            "status": "active",
                            "category": "llm",
                        }
                    else:
                        model_data = {**model_entry, "category": "llm"}

                    merged_model_data = {
                        **model_data,
                        "provider": provider_name,
                        "api_base": model_data.get("api_base", provider_api_base),
                        "api_base_env": model_data.get("api_base_env", provider_api_base_env),
                        "default_params": {
                            **inherited_defaults,
                            **(model_data.get("default_params", {}) or {}),
                        },
                    }

                    profile = ModelProfile(**merged_model_data)
                    if profile.is_active():
                        self._profiles[profile.key] = profile

                # Load Embedding models
                for model_entry in provider_data.get("embedding_models", []) or []:
                    if isinstance(model_entry, str):
                        model_id = model_entry
                        key = f"{provider_name}-embedding-{model_id}"
                        model_data = {
                            "key": key,
                            "name": model_id,
                            "model_id": model_id,
                            "status": "active",
                            "category": "embedding",
                        }
                    else:
                        model_data = {**model_entry, "category": "embedding"}

                    # Use embedding_api_base if specified, otherwise use provider api_base
                    embedding_api_base_to_use = provider_embedding_api_base if provider_embedding_api_base else provider_api_base

                    merged_model_data = {
                        **model_data,
                        "provider": provider_name,
                        "api_base": model_data.get("api_base", embedding_api_base_to_use),
                        "api_base_env": model_data.get("api_base_env", provider_api_base_env),
                        "default_params": {
                            **inherited_defaults,
                            **(model_data.get("default_params", {}) or {}),
                        },
                    }

                    profile = ModelProfile(**merged_model_data)
                    if profile.is_active():
                        self._embedding_profiles[profile.key] = profile

            logger.debug(f"Loaded {len(self._profiles)} active models from {self.config_path.name}")

        except Exception as e:
            logger.error(f"Failed to load model config: {e}", exc_info=True)
            raise

    def list_providers(self) -> list[dict[str, Any]]:
        """List all providers with their LLM models for UI display.

        Uses already-loaded _profiles to avoid re-parsing YAML.

        Returns:
            List of provider dicts with models
        """
        return self._build_providers_list(self._profiles)

    def list_providers_by_category(self, category: ModelCategory) -> list[dict[str, Any]]:
        """List providers with models filtered by category.

        Args:
            category: Model category (llm or embedding)

        Returns:
            List of provider dicts with models filtered by category
        """
        if category == ModelCategory.LLM:
            return self._build_providers_list(self._profiles)
        else:
            return self._build_providers_list(self._embedding_profiles)

    def _build_providers_list(self, profiles_map: dict[str, ModelProfile]) -> list[dict[str, Any]]:
        """Build providers list from a profiles map.

        Args:
            profiles_map: Map of model key to ModelProfile

        Returns:
            List of provider dicts with models
        """
        # Group profiles by provider
        providers_map: dict[str, list[ModelProfile]] = {}
        for profile in profiles_map.values():
            providers_map.setdefault(profile.provider, []).append(profile)

        result = []
        for provider_name, profiles in sorted(providers_map.items()):
            first_profile = profiles[0]
            provider_type = "openai-compatible"

            # Get embedding_api_base for embedding category
            embedding_api_base = None
            if first_profile.category == "embedding":
                # Try to get embedding_api_base from the original YAML
                embedding_api_base = getattr(first_profile, "embedding_api_base", None)

            models = []
            for profile in profiles:
                model_dict = {
                    "key": profile.key,
                    "name": profile.name,
                    "model_id": profile.model_id,
                    "default_params": profile.default_params,
                    "metadata": profile.metadata,
                }
                if hasattr(profile, 'category') and profile.category:
                    model_dict["category"] = profile.category
                models.append(model_dict)

            result.append(
                {
                    "provider": provider_name,
                    "name": provider_name,
                    "type": provider_type,
                    "api_base": first_profile.api_base,
                    "embedding_api_base": embedding_api_base,
                    "models": models,
                }
            )

        return result

    def list_models(self, category: ModelCategory, provider: str | None = None) -> list[dict[str, Any]]:
        """List models filtered by category and optionally by provider.

        Args:
            category: Model category (llm or embedding)
            provider: Optional provider filter

        Returns:
            List of model dicts
        """
        profiles_map = self._profiles if category == ModelCategory.LLM else self._embedding_profiles

        result = []
        for profile in profiles_map.values():
            if provider and profile.provider != provider:
                continue
            result.append({
                "key": profile.key,
                "name": profile.name,
                "model_id": profile.model_id,
                "default_params": profile.default_params,
                "metadata": profile.metadata,
            })

        return result

    def get_profile(self, model_key: str) -> ModelProfile | None:
        """Get model profile by key.

        Args:
            model_key: Model key

        Returns:
            ModelProfile instance or None
        """
        return self._profiles.get(model_key)


_registry: ModelRegistry | None = None


def get_model_registry() -> ModelRegistry:
    """Get global model registry singleton.

    Returns:
        ModelRegistry instance
    """
    global _registry
    if _registry is None:
        _registry = ModelRegistry()
    return _registry
