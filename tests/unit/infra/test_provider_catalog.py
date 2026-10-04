"""Tests for ProviderCatalog."""

from textwrap import dedent

import pytest

from apps.shared.infra.llm.provider_catalog import ProviderCatalog, get_provider_catalog
from apps.shared.llm_providers.catalog_dtos import ModelCategory


@pytest.fixture
def test_config_file(tmp_path):
    config_content = dedent(
        """
        default_params:
          temperature: 0.5
          top_p: 0.9
          max_tokens: 1000

        providers:
          - key: openai-compatible
            name: OpenAI Compatible
            api_base: https://api.openai.com/v1
            default_params:
              temperature: 0.4
            llm_models:
              - key: test-model-1
                name: Test Model 1
                model_id: gpt-3.5-turbo
                status: active

              - key: test-model-2
                name: Test Model 2
                model_id: gpt-3.5-turbo
                default_params:
                  frequency_penalty: 0.1
                status: active

              - key: deprecated-model
                name: Deprecated Model
                model_id: old-model
                status: deprecated

          - key: openai-coding
            name: OpenAI Coding
            api_base: https://coding.example.com/v1
            llm_models:
              - coding-plan

          - key: bailian
            name: Bailian
            api_base: https://dashscope.example.com/v1
            embedding_api_base: https://dashscope.example.com/v1/embeddings
            llm_models:
              - qwen-plus
            embedding_models:
              - text-embedding-v4
        """
    )
    config_file = tmp_path / "providers.yaml"
    config_file.write_text(config_content)
    return str(config_file)


class TestProviderCatalog:
    def test_load_config_with_preset_keys(self, test_config_file):
        catalog = ProviderCatalog(test_config_file)

        assert len(catalog._profiles) == 4
        assert "openai-compatible/test-model-1" in catalog._profiles
        assert "openai-compatible/test-model-2" in catalog._profiles
        assert "openai-coding/coding-plan" in catalog._profiles
        assert "openai-compatible/deprecated-model" not in catalog._profiles

    def test_provider_preset_metadata(self, test_config_file):
        catalog = ProviderCatalog(test_config_file)
        preset = catalog.get_preset("openai-compatible")

        assert preset is not None
        assert preset.key == "openai-compatible"
        assert preset.name == "OpenAI Compatible"
        assert preset.api_base == "https://api.openai.com/v1"

    def test_profile_has_provider_key(self, test_config_file):
        catalog = ProviderCatalog(test_config_file)
        profile = catalog.get_profile("openai-compatible/test-model-1")

        assert profile is not None
        assert profile.provider_key == "openai-compatible"
        assert profile.provider == "OpenAI Compatible"

    def test_list_providers_uses_stable_keys(self, test_config_file):
        catalog = ProviderCatalog(test_config_file)
        providers = catalog.list_providers()

        assert len(providers) == 3  # openai-compatible, openai-coding, bailian
        provider_keys = {provider["key"] for provider in providers}
        assert "openai-compatible" in provider_keys
        assert "openai-coding" in provider_keys
        assert all(provider["provider"] == provider["key"] for provider in providers)
        assert all(provider["name"] for provider in providers)

    def test_list_providers_includes_presets_without_catalog_models(self, tmp_path):
        config_content = dedent(
            """
            providers:
              - key: ollama
                name: Ollama (Local)
                api_base: http://127.0.0.1:11434/v1
                type: openai-compatible
                llm_models: []
                embedding_models: []
              - key: deepseek
                name: Deepseek
                api_base: https://api.deepseek.com
                type: openai-compatible
                llm_models:
                  - deepseek-v4-flash
            """
        )
        config_file = tmp_path / "providers.yaml"
        config_file.write_text(config_content)

        providers = ProviderCatalog(str(config_file)).list_providers()

        assert len(providers) == 2
        ollama = next(item for item in providers if item["key"] == "ollama")
        assert ollama["name"] == "Ollama (Local)"
        assert ollama["api_base"] == "http://127.0.0.1:11434/v1"
        assert ollama["models"] == []

    def test_list_providers_by_embedding_category(self, test_config_file):
        catalog = ProviderCatalog(test_config_file)
        providers = catalog.list_providers_by_category(ModelCategory.EMBEDDING)

        assert len(providers) == 1
        assert providers[0]["key"] == "bailian"
        assert providers[0]["embedding_api_base"] == "https://dashscope.example.com/v1/embeddings"
        assert providers[0]["models"][0]["key"] == "bailian/text-embedding-v4"

    def test_default_params_merge(self, test_config_file):
        catalog = ProviderCatalog(test_config_file)

        profile = catalog.get_profile("openai-compatible/test-model-1")
        assert profile is not None
        assert profile.get_default_temperature() == 0.4
        assert profile.get_default_top_p() == 0.9
        assert profile.get_default_max_tokens() == 1000

        profile2 = catalog.get_profile("openai-compatible/test-model-2")
        assert profile2 is not None
        assert profile2.get_default_frequency_penalty() == 0.1

    def test_string_model_format(self, tmp_path):
        config_content = dedent(
            """
            providers:
              - key: test
                name: Test Provider
                api_base: https://api.test.com/v1
                llm_models:
                  - gpt-4
                  - gpt-3.5-turbo
            """
        )
        config_file = tmp_path / "providers.yaml"
        config_file.write_text(config_content)

        catalog = ProviderCatalog(str(config_file))
        assert "test/gpt-4" in catalog._profiles
        assert catalog._profiles["test/gpt-4"].model_id == "gpt-4"

    def test_legacy_models_yaml_fallback(self, tmp_path):
        config_content = dedent(
            """
            providers:
              - provider: Legacy Provider
                api_base: https://legacy.example.com/v1
                llm_models:
                  - legacy-model
            """
        )
        legacy_file = tmp_path / "models.yaml"
        legacy_file.write_text(config_content)

        catalog = ProviderCatalog(str(legacy_file))
        preset = catalog.get_preset("legacy-provider")
        assert preset is not None
        assert preset.name == "Legacy Provider"
        assert "legacy-provider/legacy-model" in catalog._profiles

    def test_requires_providers(self, tmp_path):
        config_file = tmp_path / "providers.yaml"
        config_file.write_text("default_params:\n  temperature: 0.1\n")

        with pytest.raises(ValueError, match="'providers' is required"):
            ProviderCatalog(str(config_file))

    def test_get_provider_catalog_singleton(self):
        catalog1 = get_provider_catalog()
        catalog2 = get_provider_catalog()
        assert catalog1 is catalog2

    def test_databricks_preset_in_shipped_catalog(self):
        catalog = get_provider_catalog()
        preset = catalog.get_preset("databricks-ai-gateway")

        assert preset is not None
        assert preset.type == "openai-compatible"
        assert preset.api_base == "https://<workspace>.cloud.databricks.com/ai-gateway/mlflow/v1"
        profile = catalog.get_profile("databricks-ai-gateway/system.ai.deepseek-v4-flash-0731")
        assert profile is not None
        assert profile.model_id == "system.ai.deepseek-v4-flash-0731"
