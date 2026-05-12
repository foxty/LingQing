"""Tests for Model Registry."""

import os
from textwrap import dedent
from unittest.mock import patch

import pytest

from apps.shared.infra.llm import ModelProfile, ModelRegistry, get_model_registry


@pytest.fixture
def test_config_file(tmp_path):
    """Create a test configuration file."""
    config_content = dedent(
        """
        default_params:
          temperature: 0.5
          top_p: 0.9
          max_tokens: 1000

        providers:
          - provider: "openai-compatible"
            api_base: "https://api.openai.com/v1"
            default_params:
              temperature: 0.4
            llm_models:
              - key: "test-model-1"
                name: "Test Model 1"
                model_id: "gpt-3.5-turbo"
                status: "active"

              - key: "test-model-2"
                name: "Test Model 2"
                model_id: "gpt-3.5-turbo"
                default_params:
                  frequency_penalty: 0.1
                status: "active"

              - key: "deprecated-model"
                name: "Deprecated Model"
                model_id: "old-model"
                status: "deprecated"

          - provider: "openai-coding"
            api_base: "https://coding.example.com/v1"
            llm_models:
              - key: "coding-plan"
                name: "Coding Plan"
                model_id: "coding-plan"
                status: "active"
        """
    )
    config_file = tmp_path / "test_models.yaml"
    config_file.write_text(config_content)
    return str(config_file)


class TestModelProfile:
    """Test ModelProfile data class."""

    def test_create_profile(self):
        """Test creating a model profile."""
        profile = ModelProfile(
            key="test-key",
            name="Test Model",
            provider="openai",
            model_id="gpt-4",
            api_base="https://api.openai.com/v1",
        )

        assert profile.key == "test-key"
        assert profile.name == "Test Model"
        assert profile.provider == "openai"
        assert profile.is_active()

    def test_get_api_base_from_env(self):
        """Test getting API base from environment variable."""
        profile = ModelProfile(
            key="test",
            name="Test",
            provider="test",
            model_id="test",
            api_base="https://default.com",
            api_base_env="TEST_API_BASE",
        )

        with patch.dict(os.environ, {"TEST_API_BASE": "https://custom.com"}):
            assert profile.get_api_base() == "https://custom.com"

        with patch.dict(os.environ, {}, clear=True):
            assert profile.get_api_base() == "https://default.com"

    def test_is_active(self):
        """Test checking if model is active."""
        active_profile = ModelProfile(
            key="test",
            name="Test",
            provider="test",
            model_id="test",
            status="active",
        )
        assert active_profile.is_active()

        deprecated_profile = ModelProfile(
            key="test",
            name="Test",
            provider="test",
            model_id="test",
            status="deprecated",
        )
        assert not deprecated_profile.is_active()

    def test_default_params(self):
        """Test default params access."""
        profile = ModelProfile(
            key="test",
            name="Test",
            provider="test",
            model_id="test",
            default_params={"temperature": 0.7, "max_tokens": 1000},
        )
        assert profile.get_default_temperature() == 0.7
        assert profile.get_default_max_tokens() == 1000
        assert profile.get_default_top_p() is None


class TestModelRegistry:
    """Test ModelRegistry functionality."""

    def test_load_config(self, test_config_file):
        """Test loading configuration from file."""
        registry = ModelRegistry(test_config_file)

        assert len(registry._profiles) == 3
        assert "test-model-1" in registry._profiles
        assert "test-model-2" in registry._profiles
        assert "coding-plan" in registry._profiles
        assert "deprecated-model" not in registry._profiles

    def test_get_profile(self, test_config_file):
        """Test getting model profile."""
        registry = ModelRegistry(test_config_file)

        profile = registry.get_profile("test-model-1")
        assert profile is not None
        assert profile.key == "test-model-1"
        assert profile.name == "Test Model 1"

        profile = registry.get_profile("non-existent")
        assert profile is None

    def test_list_providers(self, test_config_file):
        """Test listing providers with models."""
        registry = ModelRegistry(test_config_file)

        providers = registry.list_providers()
        assert len(providers) == 2

        # Check first provider
        provider_keys = [p["provider"] for p in providers]
        assert "openai-compatible" in provider_keys
        assert "openai-coding" in provider_keys

        # Check models in first provider
        openai_provider = next(p for p in providers if p["provider"] == "openai-compatible")
        assert len(openai_provider["models"]) == 2
        assert openai_provider["models"][0]["key"] == "test-model-1"
        assert all(p["type"] == "openai-compatible" for p in providers)

    def test_get_profile_default_params(self, test_config_file):
        """Test that default params are merged correctly."""
        registry = ModelRegistry(test_config_file)

        profile = registry.get_profile("test-model-1")
        assert profile is not None
        # Should inherit root + provider defaults
        assert profile.get_default_temperature() == 0.4  # provider overrides
        assert profile.get_default_top_p() == 0.9  # from root
        assert profile.get_default_max_tokens() == 1000  # from root

    def test_get_profile_model_level_defaults(self, test_config_file):
        """Test model-level params merged into inherited defaults."""
        registry = ModelRegistry(test_config_file)

        profile = registry.get_profile("test-model-2")
        assert profile is not None
        assert profile.get_default_temperature() == 0.4  # from provider
        assert profile.get_default_frequency_penalty() == 0.1  # model-level

    def test_load_config_requires_providers(self):
        """Test that new config schema enforces providers key."""
        import tempfile

        config_content = dedent(
            """
            default_params:
              temperature: 0.1
            """
        )
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(config_content)
            temp_file = f.name

        try:
            with pytest.raises(ValueError, match="'providers' is required"):
                ModelRegistry(temp_file)
        finally:
            os.unlink(temp_file)

    def test_string_model_format(self, tmp_path):
        """Test that string model format works."""
        config_content = dedent(
            """
            providers:
              - provider: "test"
                api_base: "https://api.test.com/v1"
                llm_models:
                  - gpt-4
                  - gpt-3.5-turbo
            """
        )
        config_file = tmp_path / "test.yaml"
        config_file.write_text(config_content)

        registry = ModelRegistry(str(config_file))
        assert "test-gpt-4" in registry._profiles
        assert "test-gpt-3.5-turbo" in registry._profiles
        assert registry._profiles["test-gpt-4"].model_id == "gpt-4"


class TestGlobalRegistry:
    """Test global registry singleton."""

    def test_get_model_registry_singleton(self):
        """Test that get_model_registry returns singleton."""
        registry1 = get_model_registry()
        registry2 = get_model_registry()

        assert registry1 is registry2

    def test_databricks_ai_gateway_is_openai_compatible(self):
        """Databricks AI Gateway is a workspace-specific OpenAI-compatible provider."""
        registry = get_model_registry()
        providers = registry.list_providers()
        dbx = next(p for p in providers if p["provider"] == "Databricks AI Gateway")
        assert dbx["type"] == "openai-compatible"
        assert dbx["api_base"] == "https://<workspace>.cloud.databricks.com/ai-gateway/mlflow/v1"
        assert any(m["model_id"] == "system.ai.deepseek-v4-flash-0731" for m in dbx["models"])