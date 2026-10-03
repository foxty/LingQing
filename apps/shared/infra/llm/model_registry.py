"""Backward-compatible aliases for ProviderCatalog.

Prefer importing from provider_catalog directly in new code.
"""

from apps.shared.infra.llm.provider_catalog import (
    ProviderCatalog,
    ProviderPreset,
    get_provider_catalog,
)

ModelRegistry = ProviderCatalog
get_model_registry = get_provider_catalog

__all__ = [
    "ModelRegistry",
    "ProviderCatalog",
    "ProviderPreset",
    "get_model_registry",
    "get_provider_catalog",
]
