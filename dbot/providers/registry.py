"""
提供商注册表 — LLM 提供商元数据的单一事实来源。

基于协议兼容类型，而非具体厂商：
  - custom: OpenAI 协议兼容（最通用）
  - anthropic: Anthropic Claude 协议兼容
  - openrouter: 网关聚合平台（可选）

添加新协议类型：
  1. 在下面的 PROVIDERS 中添加 ProviderSpec
  2. 在 config/schema.py 中为 ProvidersConfig 添加一个字段
  完成。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ProviderSpec:
    """一个 LLM 提供商的元数据。"""

    # 身份
    name: str                       # 配置字段名
    keywords: tuple[str, ...]       # 用于匹配的模型名称关键字（小写）
    env_key: str                    # LiteLLM 环境变量
    display_name: str = ""          # 在 `dbot status` 中显示

    # 模型前缀
    litellm_prefix: str = ""                 # LiteLLM 模型前缀
    skip_prefixes: tuple[str, ...] = ()      # 跳过前缀的条件

    # 额外的环境变量
    env_extras: tuple[tuple[str, str], ...] = ()

    # 网关/本地检测
    is_gateway: bool = False                 # 是否为网关
    is_local: bool = False                   # 是否为本地部署
    detect_by_key_prefix: str = ""           # 匹配 api_key 前缀
    detect_by_base_keyword: str = ""         # 匹配 api_base URL 中的子字符串
    default_api_base: str = ""               # 默认基础 URL

    # 网关行为
    strip_model_prefix: bool = False         # 是否剥离模型前缀

    # 每个模型的参数覆盖
    model_overrides: tuple[tuple[str, dict[str, Any]], ...] = ()

    # 基于 OAuth 的提供商（不使用 API 密钥）
    is_oauth: bool = False

    # 直接提供商完全绕过 LiteLLM（例如 CustomProvider）
    is_direct: bool = False

    # 提供商支持内容块上的 cache_control
    supports_prompt_caching: bool = False

    @property
    def label(self) -> str:
        return self.display_name or self.name.title()


# ---------------------------------------------------------------------------
# PROVIDERS — 注册表。基于协议兼容类型，而非具体厂商。
# ---------------------------------------------------------------------------

PROVIDERS: tuple[ProviderSpec, ...] = (

    # === 协议兼容类型 ========================

    # Custom: OpenAI 协议兼容（最通用的兼容格式）
    # 适用于：DeepSeek、智谱、Moonshot、本地 vLLM 等所有 OpenAI 兼容 API
    ProviderSpec(
        name="custom",
        keywords=(),
        env_key="",
        display_name="Custom (OpenAI Compatible)",
        litellm_prefix="",
        is_direct=True,  # 直接使用 OpenAI SDK，绕过 LiteLLM
    ),

    # Anthropic: Claude 协议兼容
    # 适用于：Claude 官方 API、智谱 Claude 兼容模式等
    ProviderSpec(
        name="anthropic",
        keywords=("anthropic", "claude"),
        env_key="ANTHROPIC_API_KEY",
        display_name="Anthropic (Claude Compatible)",
        litellm_prefix="",
        skip_prefixes=(),
        env_extras=(),
        is_gateway=False,
        is_local=False,
        detect_by_key_prefix="",
        detect_by_base_keyword="",
        default_api_base="",
        strip_model_prefix=False,
        model_overrides=(),
        supports_prompt_caching=True,
    ),

    # OpenRouter: 网关聚合平台（可选）
    # 通过单一 API 访问数百个模型，支持 prompt caching
    ProviderSpec(
        name="openrouter",
        keywords=("openrouter",),
        env_key="OPENROUTER_API_KEY",
        display_name="OpenRouter",
        litellm_prefix="openrouter",
        skip_prefixes=(),
        env_extras=(),
        is_gateway=True,
        is_local=False,
        detect_by_key_prefix="sk-or-",
        detect_by_base_keyword="openrouter",
        default_api_base="https://openrouter.ai/api/v1",
        strip_model_prefix=False,
        model_overrides=(),
        supports_prompt_caching=True,
    ),
)


# ---------------------------------------------------------------------------
# 查找助手
# ---------------------------------------------------------------------------

def find_by_model(model: str) -> ProviderSpec | None:
    """通过模型名称关键字匹配标准提供商。"""
    model_lower = model.lower()
    model_normalized = model_lower.replace("-", "_")
    model_prefix = model_lower.split("/", 1)[0] if "/" in model_lower else ""
    normalized_prefix = model_prefix.replace("-", "_")
    std_specs = [s for s in PROVIDERS if not s.is_gateway and not s.is_local]

    # 优先使用显式提供商前缀
    for spec in std_specs:
        if model_prefix and normalized_prefix == spec.name:
            return spec

    for spec in std_specs:
        if any(kw in model_lower or kw.replace("-", "_") in model_normalized for kw in spec.keywords):
            return spec
    return None


def find_gateway(
    provider_name: str | None = None,
    api_key: str | None = None,
    api_base: str | None = None,
) -> ProviderSpec | None:
    """检测网关/本地提供商。"""
    # 1. 通过配置键直接匹配
    if provider_name:
        spec = find_by_name(provider_name)
        if spec and (spec.is_gateway or spec.is_local):
            return spec

    # 2. 通过 api_key 前缀 / api_base 关键字自动检测
    for spec in PROVIDERS:
        if spec.detect_by_key_prefix and api_key and api_key.startswith(spec.detect_by_key_prefix):
            return spec
        if spec.detect_by_base_keyword and api_base and spec.detect_by_base_keyword in api_base:
            return spec

    return None


def find_by_name(name: str) -> ProviderSpec | None:
    """通过配置字段名称查找提供商规范。"""
    for spec in PROVIDERS:
        if spec.name == name:
            return spec
    return None
