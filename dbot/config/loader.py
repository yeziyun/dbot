"""配置加载工具。"""

import json
from pathlib import Path

from dbot.config.schema import Config


def get_config_path() -> Path:
    """获取默认配置文件路径。"""
    return Path.home() / ".dbot" / "config.json"


def get_data_dir() -> Path:
    """获取 dbot 数据目录。"""
    from dbot.utils.helpers import get_data_path
    return get_data_path()


def load_config(config_path: Path | None = None) -> Config:
    """
    从文件加载配置或创建默认配置。

    参数：
        config_path：配置文件的可选路径。如果未提供，则使用默认路径。

    返回：
        加载的配置对象。
    """
    path = config_path or get_config_path()

    if path.exists():
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            data = _migrate_config(data)
            return Config.model_validate(data)
        except (json.JSONDecodeError, ValueError) as e:
            print(f"警告：无法从 {path} 加载配置：{e}")
            print("使用默认配置。")

    return Config()


def save_config(config: Config, config_path: Path | None = None) -> None:
    """
    将配置保存到文件。

    参数：
        config：要保存的配置。
        config_path：要保存到的可选路径。如果未提供，则使用默认路径。
    """
    path = config_path or get_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    data = config.model_dump(by_alias=True)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _migrate_config(data: dict) -> dict:
    """将旧配置格式迁移到当前格式。"""
    # 将 tools.exec.restrictToWorkspace 移动到 tools.restrictToWorkspace
    tools = data.get("tools", {})
    exec_cfg = tools.get("exec", {})
    if "restrictToWorkspace" in exec_cfg and "restrictToWorkspace" not in tools:
        tools["restrictToWorkspace"] = exec_cfg.pop("restrictToWorkspace")
    return data
