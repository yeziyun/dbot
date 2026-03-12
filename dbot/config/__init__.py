"""dbot 的配置模块。"""

from dbot.config.loader import get_config_path, load_config
from dbot.config.schema import Config

__all__ = ["Config", "load_config", "get_config_path"]
