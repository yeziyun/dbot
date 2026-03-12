"""Cron 类型定义。"""

from dataclasses import dataclass, field
from typing import Literal


@dataclass
class CronSchedule:
    """Cron 作业的计划定义。"""
    kind: Literal["at", "every", "cron"]
    # 用于 "at"：时间戳（毫秒）
    at_ms: int | None = None
    # 用于 "every"：间隔（毫秒）
    every_ms: int | None = None
    # 用于 "cron"：cron 表达式（例如 "0 9 * * *"）
    expr: str | None = None
    # cron 表达式的时区
    tz: str | None = None


@dataclass
class CronPayload:
    """作业运行时执行的内容。"""
    kind: Literal["system_event", "agent_turn"] = "agent_turn"
    message: str = ""
    # 将响应投递到频道
    deliver: bool = False
    channel: str | None = None  # 例如 "whatsapp"
    to: str | None = None  # 例如电话号码


@dataclass
class CronJobState:
    """作业的运行时状态。"""
    next_run_at_ms: int | None = None
    last_run_at_ms: int | None = None
    last_status: Literal["ok", "error", "skipped"] | None = None
    last_error: str | None = None


@dataclass
class CronJob:
    """一个计划任务。"""
    id: str
    name: str
    enabled: bool = True
    schedule: CronSchedule = field(default_factory=lambda: CronSchedule(kind="every"))
    payload: CronPayload = field(default_factory=CronPayload)
    state: CronJobState = field(default_factory=CronJobState)
    created_at_ms: int = 0
    updated_at_ms: int = 0
    delete_after_run: bool = False


@dataclass
class CronStore:
    """Cron 作业的持久化存储。"""
    version: int = 1
    jobs: list[CronJob] = field(default_factory=list)
