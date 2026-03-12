#!/usr/bin/env python3
"""dbot 网关启动脚本。

用法：
    python run.py

首次运行时会自动创建 ./config.json 配置文件和 ./workspace/ 工作区。
"""

import sys
from pathlib import Path

# 配置路径：当前目录
CONFIG_PATH = Path(__file__).parent / "config.json"
WORKSPACE_PATH = Path(__file__).parent / "workspace"


def ensure_config() -> Path:
    """确保配置文件存在，不存在则创建默认配置。"""
    if not CONFIG_PATH.exists():
        from dbot.config.schema import Config

        config = Config()
        # 修改默认工作区路径为相对路径
        config.agents.defaults.workspace = str(WORKSPACE_PATH.resolve())
        CONFIG_PATH.write_text(config.model_dump_json(indent=2), encoding="utf-8")
        print(f"Created config at {CONFIG_PATH}")
    return CONFIG_PATH


def ensure_workspace() -> None:
    """确保工作区目录存在。"""
    WORKSPACE_PATH.mkdir(parents=True, exist_ok=True)
    from dbot.utils.helpers import sync_workspace_templates

    sync_workspace_templates(WORKSPACE_PATH, silent=True)


def main():
    from rich.console import Console

    console = Console()

    # 初始化
    config_path = ensure_config()
    ensure_workspace()

    # 加载配置
    from dbot.config.loader import load_config

    config = load_config(config_path)

    # 显示启动信息
    console.print(f"[cyan]dbot[/cyan] Starting gateway...")
    console.print(f"  Config: {config_path}")
    console.print(f"  Workspace: {WORKSPACE_PATH.resolve()}")

    # 启动网关
    from dbot.gateway import run_gateway

    run_gateway(config, console)


if __name__ == "__main__":
    main()
