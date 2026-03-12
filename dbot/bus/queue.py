"""用于解耦渠道-代理通信的异步消息队列。"""

import asyncio

from dbot.bus.events import InboundMessage, OutboundMessage


class MessageBus:
    """
    将聊天渠道与代理核心解耦的异步消息总线。

    渠道将消息推送到入站队列，代理处理它们
    并将响应推送到出站队列。
    """

    def __init__(self):
        self.inbound: asyncio.Queue[InboundMessage] = asyncio.Queue()
        self.outbound: asyncio.Queue[OutboundMessage] = asyncio.Queue()

    async def publish_inbound(self, msg: InboundMessage) -> None:
        """将消息从渠道发布到代理。"""
        await self.inbound.put(msg)

    async def consume_inbound(self) -> InboundMessage:
        """使用下一条入站消息（阻塞直到可用）。"""
        return await self.inbound.get()

    async def publish_outbound(self, msg: OutboundMessage) -> None:
        """将响应从代理发布到渠道。"""
        await self.outbound.put(msg)

    async def consume_outbound(self) -> OutboundMessage:
        """使用下一条出站消息（阻塞直到可用）。"""
        return await self.outbound.get()

    @property
    def inbound_size(self) -> int:
        """待处理的入站消息数。"""
        return self.inbound.qsize()

    @property
    def outbound_size(self) -> int:
        """待处理的出站消息数。"""
        return self.outbound.qsize()
