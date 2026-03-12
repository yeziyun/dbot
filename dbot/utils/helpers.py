"""dbot 的实用函数。"""

import re
from datetime import datetime
from pathlib import Path


def ensure_dir(path: Path) -> Path:
    """确保目录存在，返回该路径。"""
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_data_path() -> Path:
    """~/.dbot 数据目录。"""
    return ensure_dir(Path.home() / ".dbot")


def get_workspace_path(workspace: str | None = None) -> Path:
    """解析并确保工作区路径。默认为 ~/.dbot/workspace。"""
    path = Path(workspace).expanduser() if workspace else Path.home() / ".dbot" / "workspace"
    return ensure_dir(path)


def timestamp() -> str:
    """当前 ISO 时间戳。"""
    return datetime.now().isoformat()


_UNSAFE_CHARS = re.compile(r'[<>:"/\\|?*]')

def safe_filename(name: str) -> str:
    """将不安全的路径字符替换为下划线。"""
    return _UNSAFE_CHARS.sub("_", name).strip()


def sync_workspace_templates(workspace: Path, silent: bool = False) -> list[str]:
    """将捆绑的模板同步到工作区。仅创建缺失的文件。"""
    from importlib.resources import files as pkg_files
    try:
        tpl = pkg_files("dbot") / "templates"
    except Exception:
        return []
    if not tpl.is_dir():
        return []

    added: list[str] = []

    def _write(src, dest: Path):
        if dest.exists():
            return
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(src.read_text(encoding="utf-8") if src else "", encoding="utf-8")
        added.append(str(dest.relative_to(workspace)))

    for item in tpl.iterdir():
        if item.name.endswith(".md"):
            _write(item, workspace / item.name)
    _write(tpl / "memory" / "MEMORY.md", workspace / "memory" / "MEMORY.md")
    _write(None, workspace / "memory" / "HISTORY.md")
    (workspace / "skills").mkdir(exist_ok=True)

    if added and not silent:
        from rich.console import Console
        for name in added:
            Console().print(f"  [dim]已创建 {name}[/dim]")
    return added
