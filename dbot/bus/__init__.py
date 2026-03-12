"""用于解耦渠道-代理通信的消息总线模块。"""

from dbot.bus.events import InboundMessage, OutboundMessage
from dbot.bus.queue import MessageBus

__all__ = ["MessageBus", "InboundMessage", "OutboundMessage"]
