"""用于协调聊天频道的频道管理器。"""

from __future__ import annotations

import asyncio
from typing import Any

from loguru import logger

from dbot.bus.events import OutboundMessage
from dbot.bus.queue import MessageBus
from dbot.channels.base import BaseChannel
from dbot.config.schema import Config


class ChannelManager:
    """
    管理聊天频道并协调消息路由。

    职责：
    - 初始化启用的频道（Feishu）
    - 启动/停止频道
    - 路由出站消息
    """

    def __init__(self, config: Config, bus: MessageBus):
        self.config = config
        self.bus = bus
        self.channels: dict[str, BaseChannel] = {}
        self._dispatch_task: asyncio.Task | None = None

        self._init_channels()

    def _init_channels(self) -> None:
        """根据配置初始化频道。"""

        # Feishu 频道
        if self.config.channels.feishu.enabled:
            try:
                from dbot.channels.feishu import FeishuChannel
                self.channels["feishu"] = FeishuChannel(
                    self.config.channels.feishu, self.bus
                )
                logger.info("飞书渠道已启用")
            except ImportError as e:
                logger.warning("飞书渠道不可用: {}", e)

        self._validate_allow_from()

    def _validate_allow_from(self) -> None:
        for name, ch in self.channels.items():
            if getattr(ch.config, "allow_from", None) == []:
                raise SystemExit(
                    f'错误: "{name}" 的 allowFrom 为空（拒绝所有访问）。'
                    f'设置 ["*"] 允许所有人，或添加特定用户 ID。'
                )

    async def _start_channel(self, name: str, channel: BaseChannel) -> None:
        """启动频道并记录任何异常。"""
        try:
            await channel.start()
        except Exception as e:
            logger.error("启动渠道 {} 失败: {}", name, e)

    async def start_all(self) -> None:
        """启动所有频道和出站分发器。"""
        if not self.channels:
            logger.warning("未启用任何渠道")
            return

        # 启动出站分发器
        self._dispatch_task = asyncio.create_task(self._dispatch_outbound())

        # 启动频道
        tasks = []
        for name, channel in self.channels.items():
            logger.info("正在启动 {} 渠道...", name)
            tasks.append(asyncio.create_task(self._start_channel(name, channel)))

        # 等待所有完成（它们应该永远运行）
        await asyncio.gather(*tasks, return_exceptions=True)

    async def stop_all(self) -> None:
        """停止所有频道和分发器。"""
        logger.info("正在停止所有渠道...")

        # 停止分发器
        if self._dispatch_task:
            self._dispatch_task.cancel()
            try:
                await self._dispatch_task
            except asyncio.CancelledError:
                pass

        # 停止所有频道
        for name, channel in self.channels.items():
            try:
                await channel.stop()
                logger.info("已停止 {} 渠道", name)
            except Exception as e:
                logger.error("停止 {} 失败: {}", name, e)

    async def _dispatch_outbound(self) -> None:
        """将出站消息分发到适当的频道。"""
        logger.info("出站分发器已启动")

        while True:
            try:
                msg = await asyncio.wait_for(
                    self.bus.consume_outbound(),
                    timeout=1.0
                )

                if msg.metadata.get("_progress"):
                    if msg.metadata.get("_tool_hint") and not self.config.channels.send_tool_hints:
                        continue
                    if not msg.metadata.get("_tool_hint") and not self.config.channels.send_progress:
                        continue

                channel = self.channels.get(msg.channel)
                if channel:
                    try:
                        await channel.send(msg)
                    except Exception as e:
                        logger.error("发送到 {} 失败: {}", msg.channel, e)
                else:
                    logger.warning("未知渠道: {}", msg.channel)

            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

    def get_channel(self, name: str) -> BaseChannel | None:
        """按名称获取频道。"""
        return self.channels.get(name)

    def get_status(self) -> dict[str, Any]:
        """获取所有频道的状态。"""
        return {
            name: {
                "enabled": True,
                "running": channel.is_running
            }
            for name, channel in self.channels.items()
        }

    @property
    def enabled_channels(self) -> list[str]:
        """获取启用的频道名称列表。"""
        return list(self.channels.keys())
