"""使用 Pydantic 的配置模式。"""

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel
from pydantic_settings import BaseSettings


class Base(BaseModel):
    """接受 camelCase 和 snake_case 键的基础模型。"""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class FeishuConfig(Base):
    """使用 WebSocket 长连接的飞书/Lark 渠道配置。"""

    enabled: bool = False
    app_id: str = ""  # 来自飞书开放平台的 App ID
    app_secret: str = ""  # 来自飞书开放平台的 App Secret
    encrypt_key: str = ""  # 事件订阅的加密密钥（可选）
    verification_token: str = ""  # 事件订阅的验证令牌（可选）
    allow_from: list[str] = Field(default_factory=list)  # 允许的用户 open_ids
    react_emoji: str = (
        "THUMBSUP"  # 消息反应的表情符号类型（例如 THUMBSUP, OK, DONE, SMILE）
    )


class ChannelsConfig(Base):
    """聊天渠道配置。"""

    send_progress: bool = True  # 将代理的文本进度流式传输到渠道
    send_tool_hints: bool = False  # 流式传输工具调用提示（例如 read_file("…")）
    feishu: FeishuConfig = Field(default_factory=FeishuConfig)


class AgentDefaults(Base):
    """默认代理配置。"""

    workspace: str = "~/.dbot/workspace"
    model: str = "anthropic/claude-opus-4-5"
    provider: str = (
        "auto"  # 提供商名称（custom、anthropic、openrouter）或 "auto" 用于自动检测
    )
    max_tokens: int = 8192
    temperature: float = 0.1
    max_tool_iterations: int = 40
    memory_window: int = 100
    reasoning_effort: str | None = None  # low / medium / high — 启用 LLM 思考模式


class AgentsConfig(Base):
    """代理配置。"""

    defaults: AgentDefaults = Field(default_factory=AgentDefaults)


class ProviderConfig(Base):
    """LLM 提供商配置。"""

    api_key: str = ""
    api_base: str | None = None
    extra_headers: dict[str, str] | None = None  # 自定义标头


class ProvidersConfig(Base):
    """LLM 提供商配置 - 基于协议兼容类型。"""

    custom: ProviderConfig = Field(default_factory=ProviderConfig)  # OpenAI 协议兼容
    anthropic: ProviderConfig = Field(default_factory=ProviderConfig)  # Anthropic Claude 协议兼容
    openrouter: ProviderConfig = Field(default_factory=ProviderConfig)  # 网关聚合平台（可选）


class HeartbeatConfig(Base):
    """心跳服务配置。"""

    enabled: bool = True
    interval_s: int = 30 * 60  # 30 分钟


class GatewayConfig(Base):
    """网关/服务器配置。"""

    host: str = "0.0.0.0"
    port: int = 18790
    heartbeat: HeartbeatConfig = Field(default_factory=HeartbeatConfig)


class WebSearchConfig(Base):
    """网络搜索工具配置。"""

    api_key: str = ""  # Brave Search API 密钥
    max_results: int = 5


class WebToolsConfig(Base):
    """网络工具配置。"""

    proxy: str | None = (
        None  # HTTP/SOCKS5 代理 URL，例如 "http://127.0.0.1:7890" 或 "socks5://127.0.0.1:1080"
    )
    search: WebSearchConfig = Field(default_factory=WebSearchConfig)


class ExecToolConfig(Base):
    """Shell 执行工具配置。"""

    timeout: int = 60
    path_append: str = ""


class MCPServerConfig(Base):
    """MCP 服务器连接配置（stdio 或 HTTP）。"""

    type: Literal["stdio", "sse", "streamableHttp"] | None = None  # 如果省略则自动检测
    command: str = ""  # Stdio：要运行的命令（例如 "npx"）
    args: list[str] = Field(default_factory=list)  # Stdio：命令参数
    env: dict[str, str] = Field(default_factory=dict)  # Stdio：额外的环境变量
    url: str = ""  # HTTP/SSE：端点 URL
    headers: dict[str, str] = Field(default_factory=dict)  # HTTP/SSE：自定义标头
    tool_timeout: int = 30  # 取消工具调用前的秒数


class ToolsConfig(Base):
    """工具配置。"""

    web: WebToolsConfig = Field(default_factory=WebToolsConfig)
    exec: ExecToolConfig = Field(default_factory=ExecToolConfig)
    restrict_to_workspace: bool = False  # 如果为 true，将所有工具访问限制在工作区目录
    mcp_servers: dict[str, MCPServerConfig] = Field(default_factory=dict)


class Config(BaseSettings):
    """dbot 的根配置。"""

    agents: AgentsConfig = Field(default_factory=AgentsConfig)
    channels: ChannelsConfig = Field(default_factory=ChannelsConfig)
    providers: ProvidersConfig = Field(default_factory=ProvidersConfig)
    gateway: GatewayConfig = Field(default_factory=GatewayConfig)
    tools: ToolsConfig = Field(default_factory=ToolsConfig)

    @property
    def workspace_path(self) -> Path:
        """获取扩展的工作区路径。"""
        return Path(self.agents.defaults.workspace).expanduser()

    def _match_provider(
        self, model: str | None = None
    ) -> tuple["ProviderConfig | None", str | None]:
        """匹配提供商配置及其注册表名称。返回 (config, spec_name)。"""
        from dbot.providers.registry import PROVIDERS

        forced = self.agents.defaults.provider
        if forced != "auto":
            p = getattr(self.providers, forced, None)
            return (p, forced) if p else (None, None)

        model_lower = (model or self.agents.defaults.model).lower()
        model_normalized = model_lower.replace("-", "_")
        model_prefix = model_lower.split("/", 1)[0] if "/" in model_lower else ""
        normalized_prefix = model_prefix.replace("-", "_")

        def _kw_matches(kw: str) -> bool:
            kw = kw.lower()
            return kw in model_lower or kw.replace("-", "_") in model_normalized

        # 显式提供商前缀优先
        for spec in PROVIDERS:
            p = getattr(self.providers, spec.name, None)
            if p and model_prefix and normalized_prefix == spec.name:
                if spec.is_oauth or p.api_key:
                    return p, spec.name

        # 按关键字匹配
        for spec in PROVIDERS:
            p = getattr(self.providers, spec.name, None)
            if p and any(_kw_matches(kw) for kw in spec.keywords):
                if spec.is_oauth or p.api_key:
                    return p, spec.name

        # 回退：网关优先，然后其他
        for spec in PROVIDERS:
            if spec.is_oauth:
                continue
            p = getattr(self.providers, spec.name, None)
            if p and p.api_key:
                return p, spec.name
        return None, None

    def get_provider(self, model: str | None = None) -> ProviderConfig | None:
        """获取匹配的提供商配置。"""
        p, _ = self._match_provider(model)
        return p

    def get_provider_name(self, model: str | None = None) -> str | None:
        """获取匹配的提供商的注册表名称。"""
        _, name = self._match_provider(model)
        return name

    def get_api_key(self, model: str | None = None) -> str | None:
        """获取给定模型的 API 密钥。"""
        p = self.get_provider(model)
        return p.api_key if p else None

    def get_api_base(self, model: str | None = None) -> str | None:
        """获取给定模型的 API 基础 URL。"""
        from dbot.providers.registry import find_by_name

        p, name = self._match_provider(model)
        if p and p.api_base:
            return p.api_base
        if name:
            spec = find_by_name(name)
            if spec and spec.is_gateway and spec.default_api_base:
                return spec.default_api_base
        return None

    model_config = ConfigDict(env_prefix="dbot_", env_nested_delimiter="__")
