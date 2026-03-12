"""心跳服务 - 定期唤醒代理以检查任务。"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Coroutine

from loguru import logger

if TYPE_CHECKING:
    from dbot.providers.base import LLMProvider

_HEARTBEAT_TOOL = [
    {
        "type": "function",
        "function": {
            "name": "heartbeat",
            "description": "在审查任务后报告心跳决策。",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["skip", "run"],
                        "description": "skip = 无事可做，run = 有活动任务",
                    },
                    "tasks": {
                        "type": "string",
                        "description": "活动任务的自然语言摘要（run 时必需）",
                    },
                },
                "required": ["action"],
            },
        },
    }
]


class HeartbeatService:
    """
    定期唤醒代理以检查任务的心跳服务。

    阶段 1（决策）：读取 HEARTBEAT.md 并通过虚拟工具调用询问 LLM 是否有活动任务。
    这避免了自由文本解析和不可靠的 HEARTBEAT_OK 标记。

    阶段 2（执行）：仅在阶段 1 返回 ``run`` 时触发。``on_execute`` 回调通过完整的
    代理循环运行任务并返回结果以进行投递。
    """

    def __init__(
        self,
        workspace: Path,
        provider: LLMProvider,
        model: str,
        on_execute: Callable[[str], Coroutine[Any, Any, str]] | None = None,
        on_notify: Callable[[str], Coroutine[Any, Any, None]] | None = None,
        interval_s: int = 30 * 60,
        enabled: bool = True,
    ):
        self.workspace = workspace
        self.provider = provider
        self.model = model
        self.on_execute = on_execute
        self.on_notify = on_notify
        self.interval_s = interval_s
        self.enabled = enabled
        self._running = False
        self._task: asyncio.Task | None = None

    @property
    def heartbeat_file(self) -> Path:
        return self.workspace / "HEARTBEAT.md"

    def _read_heartbeat_file(self) -> str | None:
        if self.heartbeat_file.exists():
            try:
                return self.heartbeat_file.read_text(encoding="utf-8")
            except Exception:
                return None
        return None

    async def _decide(self, content: str) -> tuple[str, str]:
        """阶段 1：通过虚拟工具调用让 LLM 决定跳过/运行。

        返回 (action, tasks)，其中 action 是 'skip' 或 'run'。
        """
        response = await self.provider.chat(
            messages=[
                {"role": "system", "content": "你是一个心跳代理。调用心跳工具来报告你的决策。"},
                {"role": "user", "content": (
                    "审查以下 HEARTBEAT.md 并确定是否有活动任务。\n\n"
                    f"{content}"
                )},
            ],
            tools=_HEARTBEAT_TOOL,
            model=self.model,
        )

        if not response.has_tool_calls:
            return "skip", ""

        args = response.tool_calls[0].arguments
        return args.get("action", "skip"), args.get("tasks", "")

    async def start(self) -> None:
        """启动心跳服务。"""
        if not self.enabled:
            logger.info("心跳服务已禁用")
            return
        if self._running:
            logger.warning("心跳服务已在运行")
            return

        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("心跳服务已启动（每 {}s）", self.interval_s)

    def stop(self) -> None:
        """停止心跳服务。"""
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None

    async def _run_loop(self) -> None:
        """主心跳循环。"""
        while self._running:
            try:
                await asyncio.sleep(self.interval_s)
                if self._running:
                    await self._tick()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("心跳错误：{}", e)

    async def _tick(self) -> None:
        """执行单次心跳检查。"""
        content = self._read_heartbeat_file()
        if not content:
            logger.debug("心跳：HEARTBEAT.md 缺失或为空")
            return

        logger.info("心跳：正在检查任务...")

        try:
            action, tasks = await self._decide(content)

            if action != "run":
                logger.info("心跳：正常（无需报告）")
                return

            logger.info("心跳：发现任务，正在执行...")
            if self.on_execute:
                response = await self.on_execute(tasks)
                if response and self.on_notify:
                    logger.info("心跳：已完成，正在投递响应")
                    await self.on_notify(response)
        except Exception:
            logger.exception("心跳执行失败")

    async def trigger_now(self) -> str | None:
        """手动触发心跳。"""
        content = self._read_heartbeat_file()
        if not content:
            return None
        action, tasks = await self._decide(content)
        if action != "run" or not self.on_execute:
            return None
        return await self.on_execute(tasks)
