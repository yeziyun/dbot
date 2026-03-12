"""聊天平台的基础频道接口。"""

from abc import ABC, abstractmethod
from typing import Any

from loguru import logger

from dbot.bus.events import InboundMessage, OutboundMessage
from dbot.bus.queue import MessageBus


class BaseChannel(ABC):
    """
    聊天频道实现的抽象基类。

    每个频道（Telegram、Discord 等）都应实现此接口
    以与 dbot 消息总线集成。
    """

    name: str = "base"

    def __init__(self, config: Any, bus: MessageBus):
        """
        初始化频道。

        参数：
            config: 特定于频道的配置。
            bus: 用于通信的消息总线。
        """
        self.config = config
        self.bus = bus
        self._running = False

    @abstractmethod
    async def start(self) -> None:
        """
        启动频道并开始监听消息。

        这应该是一个长期运行的异步任务：
        1. 连接到聊天平台
        2. 监听传入消息
        3. 通过 _handle_message() 将消息转发到总线
        """
        pass

    @abstractmethod
    async def stop(self) -> None:
        """停止频道并清理资源。"""
        pass

    @abstractmethod
    async def send(self, msg: OutboundMessage) -> None:
        """
        通过此频道发送消息。

        参数：
            msg: 要发送的消息。
        """
        pass

    def is_allowed(self, sender_id: str) -> bool:
        """检查 *sender_id* 是否被允许。空列表 → 拒绝所有；``"*"`` → 允许所有。"""
        allow_list = getattr(self.config, "allow_from", [])
        if not allow_list:
            logger.warning("{}: allow_from 为空 — 拒绝所有访问", self.name)
            return False
        if "*" in allow_list:
            return True
        sender_str = str(sender_id)
        return sender_str in allow_list or any(
            p in allow_list for p in sender_str.split("|") if p
        )

    async def _handle_message(
        self,
        sender_id: str,
        chat_id: str,
        content: str,
        media: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        session_key: str | None = None,
    ) -> None:
        """
        处理来自聊天平台的传入消息。

        此方法检查权限并转发到总线。

        参数：
            sender_id: 发送者的标识符。
            chat_id: 聊天/频道标识符。
            content: 消息文本内容。
            media: 可选的媒体 URL 列表。
            metadata: 可选的频道特定元数据。
            session_key: 可选的会话密钥覆盖（例如线程范围的会话）。
        """
        if not self.is_allowed(sender_id):
            logger.warning(
                "拒绝来自 {} 的访问（渠道 {}）。"
                "将用户添加到配置中的 allowFrom 列表以授权访问。",
                sender_id, self.name,
            )
            return

        msg = InboundMessage(
            channel=self.name,
            sender_id=str(sender_id),
            chat_id=str(chat_id),
            content=content,
            media=media or [],
            metadata=metadata or {},
            session_key_override=session_key,
        )

        await self.bus.publish_inbound(msg)

    @property
    def is_running(self) -> bool:
        """检查频道是否正在运行。"""
        return self._running
