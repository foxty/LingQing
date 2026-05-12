"""模型配置档案数据结构."""

import os
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ModelProfile:
    """模型配置档案.

    定义单个 LLM/Embedding 模型的完整配置信息，包括提供商、端点等。

    Note: API key 不再从环境变量获取，而是从 tenant.config 中获取。

    Attributes:
        key: 模型引用键，用于在代码中引用此模型（如 "gpt-4", "qwen3.5-plus"）
        name: 模型显示名称
        provider: 提供商标识（openai, qwen, hunyuan 等）
        model_id: 实际模型标识符（传给 API 的 model 参数）
        api_base: API 端点 URL（固定值，优先级低于 api_base_env）
        api_base_env: API 端点环境变量名
        default_params: 默认参数（temperature, max_tokens 等）
        status: 模型状态（active: 可用，deprecated: 已废弃）
        metadata: 额外元数据（成本、用途说明等）
        category: 模型类别（llm, embedding）
        embedding_api_base: Embedding 专用 API 端点 URL（可选）
    """

    key: str
    name: str
    provider: str
    model_id: str
    api_base: str | None = None
    api_base_env: str | None = None
    default_params: dict[str, Any] = field(default_factory=dict)
    status: str = "active"
    metadata: dict[str, Any] = field(default_factory=dict)
    category: str = "llm"  # "llm" or "embedding"
    embedding_api_base: str | None = None

    def get_api_base(self) -> str:
        """获取API端点URL.

        优先从环境变量读取，如果环境变量未设置则使用固定值。

        Returns:
            API端点URL
        """
        if self.api_base_env:
            env_value = os.getenv(self.api_base_env)
            if env_value:
                return env_value
        return self.api_base or ""

    def get_default_temperature(self) -> float:
        """获取默认温度参数.

        Returns:
            温度值
        """
        return self.default_params.get("temperature")

    def get_default_top_p(self) -> float | None:
        """获取默认top_p参数.

        Returns:
            top_p值，如果未配置返回None
        """
        return self.default_params.get("top_p")

    def get_default_max_tokens(self) -> int | None:
        """获取默认max_tokens参数.

        Returns:
            max_tokens值，如果未配置返回None
        """
        return self.default_params.get("max_tokens")

    def get_default_tool_choice(self) -> str | None:
        """获取默认tool_choice参数.

        Returns:
            tool_choice值，如果未配置返回None
        """
        return self.default_params.get("tool_choice")

    def get_default_frequency_penalty(self) -> float | None:
        """获取默认frequency_penalty参数.

        Returns:
            frequency_penalty值，如果未配置返回None
        """
        return self.default_params.get("frequency_penalty")

    def is_active(self) -> bool:
        """检查模型是否可用.

        Returns:
            True if status is 'active'
        """
        return self.status == "active"

    def __repr__(self) -> str:
        return f"ModelProfile(key='{self.key}', provider='{self.provider}', status='{self.status}')"
