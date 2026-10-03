"""Backward-compatibility tests for ModelRegistry aliases."""

from apps.shared.infra.llm import ModelRegistry, get_model_registry
from apps.shared.infra.llm.provider_catalog import ProviderCatalog, get_provider_catalog


class TestModelRegistryAliases:
    def test_model_registry_is_provider_catalog(self):
        assert ModelRegistry is ProviderCatalog

    def test_get_model_registry_is_singleton(self):
        assert get_model_registry() is get_provider_catalog()

    def test_list_providers_via_alias(self):
        registry = get_model_registry()
        providers = registry.list_providers()
        assert providers
        assert all("key" in provider for provider in providers)
        assert all("provider" in provider for provider in providers)
