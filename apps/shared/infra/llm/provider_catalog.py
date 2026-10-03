"""Provider catalog - loads platform preset providers/models from YAML.

Read-only catalog for UI wizards and preset selection. Tenant credentials and
model profiles are stored in DB (llm_providers / llm_model_profiles).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

from apps.shared.infra.llm.model_profile import ModelProfile
from apps.shared.llm_providers.catalog_dtos import ModelCategory
from apps.shared.utils.logger import get_logger

logger = get_logger(__name__)

_DEFAULT_CONFIG_NAMES = ("providers.yaml", "models.yaml")


@dataclass(frozen=True)
class ProviderPreset:
    """Platform-level provider preset from catalog YAML."""

    key: str
    name: str
    type: str
    api_base: str | None = None
    embedding_api_base: str | None = None
    api_base_env: str | None = None
    default_params: dict[str, Any] = field(default_factory=dict)


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "custom"


def _resolve_config_path(config_path: str | Path | None) -> Path:
    if config_path is not None:
        return Path(config_path)
    base_dir = Path(__file__).parent
    for name in _DEFAULT_CONFIG_NAMES:
        candidate = base_dir / name
        if candidate.exists():
            return candidate
    return base_dir / _DEFAULT_CONFIG_NAMES[0]


class ProviderCatalog:
    """Platform provider/model catalog backed by providers.yaml."""

    def __init__(self, config_path: str | Path | None = None):
        self.config_path = _resolve_config_path(config_path)
        self._presets: dict[str, ProviderPreset] = {}
        self._profiles: dict[str, ModelProfile] = {}
        self._embedding_profiles: dict[str, ModelProfile] = {}
        self._load_config()

    def _load_config(self) -> None:
        if not self.config_path.exists():
            logger.warning("Provider catalog file not found: %s", self.config_path)
            return

        with open(self.config_path) as f:
            config = yaml.safe_load(f) or {}

        global_default_params = config.get("default_params", {}) or {}
        providers = config.get("providers", []) or []
        if not providers:
            raise ValueError(f"Invalid {self.config_path.name}: 'providers' is required and must be non-empty")

        for provider_data in providers:
            display_name = provider_data.get("name") or provider_data.get("provider")
            if not display_name:
                raise ValueError("Invalid provider config: 'name' or 'provider' is required")

            preset_key = provider_data.get("key") or _slugify(display_name)
            provider_type = provider_data.get("type", "openai-compatible")
            provider_api_base = provider_data.get("api_base")
            provider_api_base_env = provider_data.get("api_base_env")
            provider_embedding_api_base = provider_data.get("embedding_api_base")
            provider_default_params = provider_data.get("default_params", {}) or {}
            inherited_defaults = {**global_default_params, **provider_default_params}

            self._presets[preset_key] = ProviderPreset(
                key=preset_key,
                name=display_name,
                type=provider_type,
                api_base=provider_api_base,
                embedding_api_base=provider_embedding_api_base,
                api_base_env=provider_api_base_env,
                default_params=inherited_defaults,
            )

            self._load_models_for_provider(
                provider_data=provider_data,
                preset_key=preset_key,
                display_name=display_name,
                provider_api_base=provider_api_base,
                provider_api_base_env=provider_api_base_env,
                provider_embedding_api_base=provider_embedding_api_base,
                inherited_defaults=inherited_defaults,
                category="llm",
                target=self._profiles,
            )
            self._load_models_for_provider(
                provider_data=provider_data,
                preset_key=preset_key,
                display_name=display_name,
                provider_api_base=provider_api_base,
                provider_api_base_env=provider_api_base_env,
                provider_embedding_api_base=provider_embedding_api_base,
                inherited_defaults=inherited_defaults,
                category="embedding",
                target=self._embedding_profiles,
            )

        logger.debug(
            "Loaded %s LLM and %s embedding catalog models from %s",
            len(self._profiles),
            len(self._embedding_profiles),
            self.config_path.name,
        )

    def _load_models_for_provider(
        self,
        *,
        provider_data: dict[str, Any],
        preset_key: str,
        display_name: str,
        provider_api_base: str | None,
        provider_api_base_env: str | None,
        provider_embedding_api_base: str | None,
        inherited_defaults: dict[str, Any],
        category: str,
        target: dict[str, ModelProfile],
    ) -> None:
        models_key = "llm_models" if category == "llm" else "embedding_models"
        for model_entry in provider_data.get(models_key, []) or []:
            if isinstance(model_entry, str):
                model_id = model_entry
                model_key = model_entry
                model_data: dict[str, Any] = {
                    "key": model_key,
                    "name": model_id,
                    "model_id": model_id,
                    "status": "active",
                    "category": category,
                }
            else:
                model_data = {**model_entry, "category": category}
                model_key = model_data.get("key") or model_data.get("model_id")
                if not model_key:
                    raise ValueError(f"Invalid model config under {preset_key}: 'key' or 'model_id' is required")

            catalog_model_key = f"{preset_key}/{model_key}"
            embedding_api_base = provider_embedding_api_base if category == "embedding" else None
            default_api_base = embedding_api_base or provider_api_base

            merged_model_data = {
                **model_data,
                "key": catalog_model_key,
                "provider": display_name,
                "provider_key": preset_key,
                "api_base": model_data.get("api_base", default_api_base),
                "api_base_env": model_data.get("api_base_env", provider_api_base_env),
                "embedding_api_base": embedding_api_base,
                "default_params": {
                    **inherited_defaults,
                    **(model_data.get("default_params", {}) or {}),
                },
            }

            profile = ModelProfile(**merged_model_data)
            if profile.is_active():
                target[profile.key] = profile

    def get_preset(self, preset_key: str) -> ProviderPreset | None:
        return self._presets.get(preset_key)

    def list_presets(self) -> list[ProviderPreset]:
        return sorted(self._presets.values(), key=lambda preset: preset.name)

    def list_providers(self) -> list[dict[str, Any]]:
        """List all provider presets with LLM catalog models (models may be empty)."""
        grouped = self._group_profiles(self._profiles)
        return [
            self._preset_entry(preset, grouped.get(preset.key, []))
            for preset in sorted(self._presets.values(), key=lambda item: item.name)
        ]

    def list_providers_by_category(self, category: ModelCategory) -> list[dict[str, Any]]:
        profiles_map = self._profiles if category == ModelCategory.LLM else self._embedding_profiles
        return self._build_providers_list(profiles_map)

    @staticmethod
    def _group_profiles(profiles_map: dict[str, ModelProfile]) -> dict[str, list[ModelProfile]]:
        grouped: dict[str, list[ModelProfile]] = {}
        for profile in profiles_map.values():
            grouped.setdefault(profile.provider_key or profile.provider, []).append(profile)
        return grouped

    def _preset_entry(self, preset: ProviderPreset, profiles: list[ModelProfile]) -> dict[str, Any]:
        first_profile = profiles[0] if profiles else None
        return {
            "key": preset.key,
            "provider": preset.key,
            "name": preset.name,
            "type": preset.type,
            "api_base": preset.api_base or (first_profile.api_base if first_profile else None),
            "embedding_api_base": preset.embedding_api_base
            or (getattr(first_profile, "embedding_api_base", None) if first_profile else None),
            "models": [self._profile_summary(profile) for profile in profiles],
        }

    @staticmethod
    def _profile_summary(profile: ModelProfile) -> dict[str, Any]:
        return {
            "key": profile.key,
            "name": profile.name,
            "model_id": profile.model_id,
            "default_params": profile.default_params,
            "metadata": profile.metadata,
            "category": profile.category,
        }

    def _build_providers_list(self, profiles_map: dict[str, ModelProfile]) -> list[dict[str, Any]]:
        grouped = self._group_profiles(profiles_map)

        result: list[dict[str, Any]] = []
        for preset_key in sorted(grouped.keys(), key=lambda key: self._presets.get(key, ProviderPreset(key, key, "openai-compatible")).name):
            preset = self._presets.get(preset_key)
            if preset is None:
                continue
            result.append(self._preset_entry(preset, grouped[preset_key]))

        return result

    def list_models(self, category: ModelCategory, provider: str | None = None) -> list[dict[str, Any]]:
        profiles_map = self._profiles if category == ModelCategory.LLM else self._embedding_profiles
        result: list[dict[str, Any]] = []
        for profile in profiles_map.values():
            if provider and profile.provider_key != provider and profile.provider != provider:
                continue
            result.append(
                {
                    "key": profile.key,
                    "name": profile.name,
                    "model_id": profile.model_id,
                    "default_params": profile.default_params,
                    "metadata": profile.metadata,
                    "category": profile.category,
                }
            )
        return result

    def get_profile(self, catalog_model_key: str) -> ModelProfile | None:
        return self._profiles.get(catalog_model_key) or self._embedding_profiles.get(catalog_model_key)


_catalog: ProviderCatalog | None = None


def get_provider_catalog() -> ProviderCatalog:
    global _catalog
    if _catalog is None:
        _catalog = ProviderCatalog()
    return _catalog
