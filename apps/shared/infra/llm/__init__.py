"""LLM基础设施 - 模型配置和管理.

提供统一的LLM模型访问接口，支持：
- 多提供商模型配置（OpenAI-compatible, Qwen 等）
- 模型配置热加载
- 模型使用统计
"""

from apps.shared.infra.llm.model_profile import ModelProfile
from apps.shared.infra.llm.model_registry import ModelRegistry, get_model_registry

__all__ = [
    "ModelProfile",
    "ModelRegistry",
    "get_model_registry",
]
