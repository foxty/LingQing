"""Tests for LLMModelFactory OpenAI-compatible creation."""

from unittest.mock import MagicMock, patch

from apps.shared.infra.llm.llm_model_factory import LLMModelFactory
from apps.shared.schemas.model_config import ModelConfigDTO
from apps.shared.utils.field_cipher import FieldCipher


def _encrypted_config(api_base: str, model_type: str = "openai-compatible") -> dict:
    cipher = FieldCipher()
    return {
        "llm_config": {
            "agent_model": {
                "name": "test",
                "type": model_type,
                "api_base": api_base,
                "api_key": cipher.encrypt("token"),
                "model_id": "system.ai.deepseek-v4-flash-0731",
            }
        }
    }


class TestLLMModelFactory:
    def test_legacy_databricks_type_normalizes(self):
        config = ModelConfigDTO(
            name="legacy",
            type="databricks",
            api_base="https://dbc-example.cloud.databricks.com/ai-gateway/mlflow/v1",
            api_key="token",
            model_id="system.ai.deepseek-v4-flash-0731",
        )
        assert config.type == "openai-compatible"

    @patch("langchain_openai.ChatOpenAI")
    def test_databricks_gateway_uses_chat_openai(self, mock_chat):
        mock_chat.return_value = MagicMock()
        factory = LLMModelFactory(
            _encrypted_config(
                "https://dbc-e61807ff-edc4.cloud.databricks.com/ai-gateway/mlflow/v1",
                model_type="databricks",
            )
        )

        factory.get_agent_model()

        kwargs = mock_chat.call_args.kwargs
        assert kwargs["model"] == "system.ai.deepseek-v4-flash-0731"
        assert kwargs["base_url"] == "https://dbc-e61807ff-edc4.cloud.databricks.com/ai-gateway/mlflow/v1"
        assert kwargs["api_key"] == "token"
        assert kwargs["stream_usage"] is False
        assert "extra_body" not in kwargs
        assert factory._agent_model is not None
        assert factory._agent_model.type == "openai-compatible"

    def test_model_id_and_max_tokens_accessors(self):
        cipher = FieldCipher()
        factory = LLMModelFactory(
            {
                "llm_config": {
                    "agent_model": {
                        "name": "agent",
                        "type": "openai-compatible",
                        "api_base": "https://example.com/v1",
                        "api_key": cipher.encrypt("token"),
                        "model_id": "system.ai.deepseek-v4-flash-0731",
                        "params": {"max_tokens": 4000},
                    },
                    "mini_agent_model": {
                        "name": "mini",
                        "type": "openai-compatible",
                        "api_base": "https://example.com/v1",
                        "api_key": cipher.encrypt("token"),
                        "model_id": "mini-model",
                    },
                }
            }
        )

        assert factory.get_agent_model_id() == "system.ai.deepseek-v4-flash-0731"
        assert factory.get_mini_agent_model_id() == "mini-model"
        assert factory.get_agent_max_output_tokens() == 4000

    @patch("langchain_openai.ChatOpenAI")
    def test_openai_compatible_disables_thinking(self, mock_chat):
        mock_chat.return_value = MagicMock()
        factory = LLMModelFactory(_encrypted_config("https://dashscope.aliyuncs.com/compatible-mode/v1"))

        factory.get_agent_model()

        assert mock_chat.call_args.kwargs["extra_body"] == {"thinking": {"type": "disabled"}}
