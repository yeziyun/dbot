"""dbot 网关启动逻辑。"""

import asyncio
from pathlib import Path

from rich.console import Console

from dbot import __logo__
from dbot.config.schema import Config


def make_provider(config: Config, console: Console | None = None):
    """从配置创建适当的 LLM 提供商。"""
    from dbot.providers.custom_provider import CustomProvider
    from dbot.providers.litellm_provider import LiteLLMProvider

    model = config.agents.defaults.model
    provider_name = config.get_provider_name(model)
    p = config.get_provider(model)

    # 自定义：直接的 OpenAI 兼容端点，绕过 LiteLLM
    if provider_name == "custom":
        return CustomProvider(
            api_key=p.api_key if p else "no-key",
            api_base=config.get_api_base(model) or "http://localhost:8000/v1",
            default_model=model,
        )

    from dbot.providers.registry import find_by_name

    spec = find_by_name(provider_name)
    if (
        not model.startswith("bedrock/")
        and not (p and p.api_key)
        and not (spec and spec.is_oauth)
    ):
        if console:
            console.print("[red]错误：未配置 API 密钥。[/red]")
            console.print("在 config.json 的 providers 部分设置一个")
        raise SystemExit(1)

    return LiteLLMProvider(
        api_key=p.api_key if p else None,
        api_base=config.get_api_base(model),
        default_model=model,
        extra_headers=p.extra_headers if p else None,
        provider_name=provider_name,
    )


def run_gateway(config: Config, console: Console | None = None, verbose: bool = False):
    """启动 dbot 网关服务。"""
    from dbot.agent.loop import AgentLoop
    from dbot.bus.queue import MessageBus
    from dbot.channels.manager import ChannelManager
    from dbot.cron.service import CronService
    from dbot.cron.types import CronJob
    from dbot.heartbeat.service import HeartbeatService
    from dbot.session.manager import SessionManager
    from dbot.utils.helpers import sync_workspace_templates

    if console is None:
        console = Console()

    if verbose:
        import logging

        logging.basicConfig(level=logging.DEBUG)

    sync_workspace_templates(config.workspace_path)
    bus = MessageBus()
    provider = make_provider(config, console)
    session_manager = SessionManager(config.workspace_path)

    # 首先创建 cron 服务（在创建代理后设置回调）
    # 使用工作区路径进行每实例 cron 存储
    cron_store_path = config.workspace_path / "cron" / "jobs.json"
    cron = CronService(cron_store_path)

    # 使用 cron 服务创建代理
    agent = AgentLoop(
        bus=bus,
        provider=provider,
        workspace=config.workspace_path,
        model=config.agents.defaults.model,
        temperature=config.agents.defaults.temperature,
        max_tokens=config.agents.defaults.max_tokens,
        max_iterations=config.agents.defaults.max_tool_iterations,
        memory_window=config.agents.defaults.memory_window,
        reasoning_effort=config.agents.defaults.reasoning_effort,
        brave_api_key=config.tools.web.search.api_key or None,
        web_proxy=config.tools.web.proxy or None,
        exec_config=config.tools.exec,
        cron_service=cron,
        restrict_to_workspace=config.tools.restrict_to_workspace,
        session_manager=session_manager,
        mcp_servers=config.tools.mcp_servers,
        channels_config=config.channels,
    )

    # 设置 cron 回调（需要代理）
    async def on_cron_job(job: CronJob) -> str | None:
        """通过代理执行 cron 作业。"""
        from dbot.agent.tools.cron import CronTool
        from dbot.agent.tools.message import MessageTool

        reminder_note = (
            "[定时任务] 计时器结束。\n\n"
            f"任务 '{job.name}' 已触发。\n"
            f"计划指令: {job.payload.message}"
        )

        # 防止代理在执行期间调度新的 cron 作业
        cron_tool = agent.tools.get("cron")
        cron_token = None
        if isinstance(cron_tool, CronTool):
            cron_token = cron_tool.set_cron_context(True)
        try:
            response = await agent.process_direct(
                reminder_note,
                session_key=f"cron:{job.id}",
                channel=job.payload.channel or "cli",
                chat_id=job.payload.to or "direct",
            )
        finally:
            if isinstance(cron_tool, CronTool) and cron_token is not None:
                cron_tool.reset_cron_context(cron_token)

        message_tool = agent.tools.get("message")
        if isinstance(message_tool, MessageTool) and message_tool._sent_in_turn:
            return response

        if job.payload.deliver and job.payload.to and response:
            from dbot.bus.events import OutboundMessage

            await bus.publish_outbound(
                OutboundMessage(
                    channel=job.payload.channel or "cli",
                    chat_id=job.payload.to,
                    content=response,
                )
            )
        return response

    cron.on_job = on_cron_job

    # 创建渠道管理器
    channels = ChannelManager(config, bus)

    def _pick_heartbeat_target() -> tuple[str, str]:
        """为心跳触发的消息选择可路由的渠道/聊天目标。"""
        enabled = set(channels.enabled_channels)
        # 优先选择已启用渠道上最近更新的非内部会话。
        for item in session_manager.list_sessions():
            key = item.get("key") or ""
            if ":" not in key:
                continue
            channel, chat_id = key.split(":", 1)
            if channel in {"cli", "system"}:
                continue
            if channel in enabled and chat_id:
                return channel, chat_id
        # 回退保持先前的行为但保持显式。
        return "cli", "direct"

    # 创建心跳服务
    async def on_heartbeat_execute(tasks: str) -> str:
        """阶段 2：通过完整的代理循环执行心跳任务。"""
        channel, chat_id = _pick_heartbeat_target()

        async def _silent(*_args, **_kwargs):
            pass

        return await agent.process_direct(
            tasks,
            session_key="heartbeat",
            channel=channel,
            chat_id=chat_id,
            on_progress=_silent,
        )

    async def on_heartbeat_notify(response: str) -> None:
        """将心跳响应传递到用户的渠道。"""
        from dbot.bus.events import OutboundMessage

        channel, chat_id = _pick_heartbeat_target()
        if channel == "cli":
            return  # 没有可用的外部渠道来传递
        await bus.publish_outbound(
            OutboundMessage(channel=channel, chat_id=chat_id, content=response)
        )

    hb_cfg = config.gateway.heartbeat
    heartbeat = HeartbeatService(
        workspace=config.workspace_path,
        provider=provider,
        model=agent.model,
        on_execute=on_heartbeat_execute,
        on_notify=on_heartbeat_notify,
        interval_s=hb_cfg.interval_s,
        enabled=hb_cfg.enabled,
    )

    if channels.enabled_channels:
        console.print(
            f"[green]✓[/green] 已启用渠道: {', '.join(channels.enabled_channels)}"
        )
    else:
        console.print("[yellow]警告: 未启用任何渠道[/yellow]")

    cron_status = cron.status()
    if cron_status["jobs"] > 0:
        console.print(f"[green]✓[/green] Cron: {cron_status['jobs']} 个计划任务")

    console.print(f"[green]✓[/green] 心跳: 每 {hb_cfg.interval_s} 秒")

    async def run():
        try:
            await cron.start()
            await heartbeat.start()
            await asyncio.gather(
                agent.run(),
                channels.start_all(),
            )
        except KeyboardInterrupt:
            console.print("\n正在关闭...")
        finally:
            await agent.close_mcp()
            heartbeat.stop()
            cron.stop()
            agent.stop()
            await channels.stop_all()

    asyncio.run(run())
